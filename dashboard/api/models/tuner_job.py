import json
import logging
from datetime import datetime
from pathlib import Path

from cachetools import TTLCache
from clients import tuner
from enums import JobStatus
from extensions import db
from requests import HTTPError
from sqlalchemy import Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .experiment import Experiment

logger = logging.getLogger(__name__)
status_cache: TTLCache = TTLCache(maxsize=100, ttl=30)  # 30s TTL for normal operation
_last_known_status: dict[int, dict] = {}  # Fallback cache for failures (job_id -> status)


class TunerJob(db.Model):  # type: ignore
    """Tuner job for optimizing GROMACS simulation parameters."""

    __tablename__ = "tuner_jobs"

    # Local auto-incrementing ID
    # TODO: use the `tuner_run_id` as primary key (breaks db migration)
    id: Mapped[int] = mapped_column(db.Integer, primary_key=True, autoincrement=True)
    # ID of the tune job from the tuner API (set after submission)
    tuner_run_id: Mapped[str | None] = mapped_column(db.String(36), nullable=True)
    # ID of the experiment this job belongs to
    experiment_id: Mapped[str] = mapped_column(db.String(5), db.ForeignKey("experiments.id"))
    # name of the TPR file being tuned
    tpr_name: Mapped[str] = mapped_column(db.String(255), nullable=False)
    # error message if job creation failed
    error_message: Mapped[str | None] = mapped_column(db.String(512), nullable=True)
    # creation time
    created_at: Mapped[datetime] = mapped_column(db.DateTime, default=datetime.now)
    # whether the job was stopped (preserves data but job is deleted from tuner)
    is_stopped: Mapped[bool] = mapped_column(db.Boolean, default=False, nullable=False)
    # preserved status data when job is stopped
    # TODO: use the JSON type from SQLAlchemy (breaks db migration)
    _preserved_summary: Mapped[str] = mapped_column("preserved_summary", Text, nullable=True)
    # TODO: use the JSON type from SQLAlchemy (breaks db migration)
    _preserved_trials: Mapped[str] = mapped_column("preserved_trials", Text, nullable=True)
    _preserved_cluster_resources: Mapped[str] = mapped_column(
        "preserved_cluster_resources", db.String(255), nullable=True
    )

    # back-reference to the parent experiment
    experiment: Mapped["Experiment"] = relationship("Experiment", back_populates="tuner_jobs")

    @property
    def tuner_status(self) -> JobStatus:
        """Status of the job on the tuner."""
        return self._status().get("status", JobStatus.UNKNOWN)

    @property
    def summary(self) -> dict:
        """Summary of the tuner trial statuses."""
        if self.is_stopped and self._preserved_summary:
            return json.loads(self._preserved_summary)
        return self._status().get("summary", {})

    @property
    def trials(self) -> list[dict]:
        """Trial jobs with their statuses."""
        if self.is_stopped and self._preserved_trials:
            return json.loads(self._preserved_trials)
        return self._status().get("trials", [])

    @property
    def cluster_resources(self) -> str:
        """Cluster resources used by the tuner jobs."""
        if self.is_stopped and self._preserved_cluster_resources:
            return self._preserved_cluster_resources
        return self._status().get("cluster_resources", "N/A")

    def _status(self) -> dict:
        """
        Fetch tuner job status with caching and fallback on errors.

        Uses a TTL cache for normal operation and falls back to last known
        status on timeout or other errors to prevent breaking dependent code.
        """
        if self.is_stopped or not self.tuner_run_id:
            return {}

        cache_key = self.id

        # Return cached value if still fresh
        if cache_key in status_cache:
            return status_cache[cache_key]

        try:
            status = tuner.poll_status(self.tuner_run_id)
            if err_msg := status.get("error"):
                self.error_message = err_msg
                db.session.commit()

            # Validate response completeness
            if "status" not in status or "trials" not in status:
                raise ValueError(f"Incomplete status response from tuner for job {self.tuner_run_id}")

            # Update both caches on success
            status_cache[cache_key] = status
            _last_known_status[cache_key] = status
            return status

        except TimeoutError:
            logger.warning(f"Timeout fetching tuner status for job {self.tuner_run_id}")
        except Exception:
            logger.exception(f"Error fetching tuner status for job {self.tuner_run_id}")

        # Return last known status if available, empty dict otherwise
        return _last_known_status.get(cache_key, {})

    @classmethod
    def start(cls, experiment: Experiment, tpr_path: Path, nsteps: int = 25000, extra_args: str = "") -> "TunerJob":
        """
        Start a tuner job for the given experiment and TPR file.

        Args:
            experiment: The parent experiment.
            tpr_path: Path to the TPR file.
            nsteps: Number of steps for tuning runs (default: 25000, which is 50 ps).
            extra_args: Additional GROMACS mdrun arguments (default: "").

        Returns:
            The created TunerJob instance.
        """
        # Create job record
        job: TunerJob = cls(tpr_name=tpr_path.name, experiment=experiment)  # type: ignore[call-arg]
        db.session.add(job)
        db.session.commit()

        try:
            # Submit directly to tuner with nsteps and extra_args
            response = tuner.run_submit(tpr_path, nsteps=nsteps, extra_args=extra_args)
            job.tuner_run_id = response["id"]
            db.session.commit()
            logger.info(f"Tuner job {response['id']} started for experiment {experiment.id}")
        except Exception as e:
            logger.exception(f"Failed to submit tuner job: {e}")
            job.error_message = f"Failed to submit to tuner: {e!s}"
            db.session.commit()

        return job

    def stop(self) -> None:
        """
        Stop the tuner job and preserve its current status.

        The job gets deleted from the tuner but data is preserved in the database.
        """
        if self.is_stopped:
            return

        current_status = self._status()

        # Only preserve trials with performance data
        trials = [trial for trial in current_status.get("trials", []) if trial.get("performance") is not None]

        # Update summary counts
        summary = current_status.get("summary", {})
        summary["TERMINATED"] = len(trials)
        summary["RUNNING"] = 0

        self._preserved_summary = json.dumps(summary)
        self._preserved_trials = json.dumps(trials)
        self._preserved_cluster_resources = current_status.get("cluster_resources", "N/A")
        self.is_stopped = True

        if self.tuner_run_id:
            try:
                tuner.delete_job(self.tuner_run_id)
            except HTTPError:
                logger.exception(f"Failed to delete tuner job {self.tuner_run_id}")

        status_cache.clear()
        logger.info(f"Stopped tuner job {self.tuner_run_id}")

    def delete(self) -> None:
        """
        Delete the tuner job completely.

        If running, deletes from tuner API.
        If stopped, does nothing on tuner API.
        """
        if self.is_stopped or not self.tuner_run_id:
            return

        try:
            tuner.delete_job(self.tuner_run_id)
        except HTTPError:
            logger.exception(f"Failed to delete tuner job {self.tuner_run_id}")
