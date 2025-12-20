import json
import logging
import time
from datetime import datetime
from pathlib import Path
from typing import Callable

from cachetools import TTLCache, cached
from clients import k8s, tuner
from config import GMX_IMAGE
from extensions import db
from flask import current_app
from requests import HTTPError
from sqlalchemy import Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .experiment import Experiment

logger = logging.getLogger(__name__)
status_cache: TTLCache = TTLCache(maxsize=100, ttl=0.2)  # 200ms


class TunerJob(db.Model):  # type: ignore
    """Tuner job for optimizing GROMACS simulation parameters."""

    __tablename__ = "tuner_jobs"

    # Local auto-incrementing ID
    id: Mapped[int] = mapped_column(db.Integer, primary_key=True, autoincrement=True)
    # ID of the tune job from the tuner API (set after submission)
    tuner_run_id: Mapped[str | None] = mapped_column(db.String(36), nullable=True)
    # ID of the experiment this job belongs to
    experiment_id: Mapped[str] = mapped_column(db.String(5), db.ForeignKey("experiments.id"))
    # name of the TPR file being tuned
    tpr_name: Mapped[str] = mapped_column(db.String(255), nullable=False)
    # whether the job is pending TPR modification
    is_pending: Mapped[bool] = mapped_column(db.Boolean, default=True, nullable=False)
    # error message if job creation failed
    error_message: Mapped[str | None] = mapped_column(db.String(512), nullable=True)
    # creation time
    created_at: Mapped[datetime] = mapped_column(db.DateTime, default=datetime.now)
    # whether the job was stopped (preserves data but job is deleted from tuner)
    is_stopped: Mapped[bool] = mapped_column(db.Boolean, default=False, nullable=False)
    # preserved status data when job is stopped
    _preserved_summary: Mapped[str] = mapped_column("preserved_summary", Text, nullable=True)
    _preserved_trials: Mapped[str] = mapped_column("preserved_trials", Text, nullable=True)
    _preserved_cluster_resources: Mapped[str] = mapped_column(
        "preserved_cluster_resources", db.String(255), nullable=True
    )

    # back-reference to the parent experiment
    experiment: Mapped["Experiment"] = relationship("Experiment", back_populates="tuner_jobs")

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

    @cached(cache=status_cache)
    def _status(self) -> dict:
        if self.is_stopped or self.is_pending or not self.tuner_run_id:
            return {}
        try:
            return tuner.poll_status(self.tuner_run_id)
        except Exception:
            logger.exception(f"Failed to fetch status for tuner job {self.tuner_run_id}")
            return {}

    @staticmethod
    def _modify_tpr_async(
        experiment_id: str,
        input_tpr_name: str,
        output_tpr_name: str,
        nsteps: int,
        on_success: Callable,
        on_error: Callable,
    ) -> None:
        """
        Modify a TPR file by running gmx convert-tpr in a K8s job (async with callbacks).

        Args:
            experiment_id: The experiment ID.
            input_tpr_name: Name of the input TPR file.
            output_tpr_name: Name of the output TPR file.
            nsteps: Number of simulation steps.
            on_success: Callback to call when TPR modification succeeds.
            on_error: Callback to call when TPR modification fails.
        """
        job_name = f"tpr-mod-{experiment_id}-{int(time.time())}"
        command = f"gmx convert-tpr -s {input_tpr_name} -o {output_tpr_name} -nsteps {nsteps}"

        logger.info(f"Starting TPR modification for experiment {experiment_id} with nsteps={nsteps}")
        k8s.create_job(job_name, GMX_IMAGE, experiment_id, command)

        def success() -> None:
            k8s.delete_job(job_name)
            on_success()

        def error(error: Exception) -> None:
            k8s.delete_job(job_name)
            on_error(error)

        k8s.wait_for_job(job_name, success, error, timeout=60)

    @classmethod
    def start(cls, experiment: Experiment, tpr_path: Path, nsteps: int = 25000) -> "TunerJob":
        """
        Start a tuner job for the given experiment and TPR file (async).

        Creates the job record immediately in pending state, then modifies TPR in background.

        Args:
            experiment: The parent experiment.
            tpr_path: Path to the TPR file.
            nsteps: Number of steps for tuning runs (default: 25000, which is 50 ps).

        Returns:
            The created TunerJob instance (in pending state).
        """
        # Create job immediately in pending state
        job: TunerJob = cls(tpr_name=tpr_path.name, experiment=experiment, is_pending=True)  # type: ignore[call-arg]
        db.session.add(job)
        db.session.commit()

        tuning_tpr_name = f"{tpr_path.stem}_tuning_{job.id}.tpr"
        tuning_tpr_path = tpr_path.parent / tuning_tpr_name

        app = current_app._get_current_object()  # type: ignore[attr-defined]  # noqa: SLF001

        def on_tpr_ready() -> None:
            """Submit to tuner when TPR modification completes."""
            with app.app_context():
                fresh_job = db.session.get(TunerJob, job.id)
                if not fresh_job:
                    logger.info(f"Tuner job {job.id} was deleted, skipping submission")
                    return

                try:
                    response = tuner.run_submit(tuning_tpr_path)
                    fresh_job.tuner_run_id = response["tuner_run_id"]
                    fresh_job.is_pending = False
                    db.session.commit()
                    logger.info(f"Tuner job {response['tuner_run_id']} started for experiment {experiment.id}")
                except Exception as e:
                    logger.exception(f"Failed to submit tuner job: {e}")
                    fresh_job.is_pending = False
                    fresh_job.error_message = f"Failed to submit to tuner: {e!s}"
                    db.session.commit()
                finally:
                    tuning_tpr_path.unlink(missing_ok=True)

        def on_tpr_error(error: Exception) -> None:
            """Handle TPR modification failure."""
            with app.app_context():
                logger.error(f"TPR modification failed: {error}")
                fresh_job = db.session.get(TunerJob, job.id)
                if fresh_job:
                    fresh_job.is_pending = False
                    fresh_job.error_message = f"TPR modification failed: {error!s}"
                    db.session.commit()

        # Start async TPR modification
        cls._modify_tpr_async(experiment.id, tpr_path.name, tuning_tpr_name, nsteps, on_tpr_ready, on_tpr_error)

        return job

    def stop(self) -> None:
        """
        Stop the tuner job and preserve its current status.

        The job gets deleted from the tuner but data is preserved in the database.
        """
        if self.is_stopped or self.is_pending:
            return

        current_status = self._status()

        # Convert RUNNING trials to TERMINATED
        trials = current_status.get("trials", [])
        for trial in trials:
            if trial.get("status") == "RUNNING":
                trial["status"] = "TERMINATED"

        # Update summary counts
        summary = current_status.get("summary", {})
        terminated_count = summary.get("TERMINATED", 0) + summary.get("RUNNING", 0)
        summary["TERMINATED"] = terminated_count
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
        If pending or stopped, does nothing on tuner API.
        """
        if not self.is_stopped and not self.is_pending and self.tuner_run_id:
            try:
                tuner.delete_job(self.tuner_run_id)
            except HTTPError:
                logger.exception(f"Failed to delete tuner job {self.tuner_run_id}")
