import logging
from datetime import UTC, datetime
from http import HTTPStatus

from cache import tuner_last_known_status, tuner_status_cache
from clients import tuner
from enums import Engine, JobStatus
from extensions import db
from requests import HTTPError
from sqlalchemy import JSON
from sqlalchemy.orm import Mapped, mapped_column, relationship

from models.simulation import (
    get_simulation,
    mark_simulation_readonly,
    resolve_simulation_role,
    validate_simulation_for_action,
)

from .experiment import Experiment

logger = logging.getLogger(__name__)


class TunerJob(db.Model):  # type: ignore
    """Tuner job for optimizing MD simulation parameters (GROMACS or AMBER)."""

    __tablename__ = "tuner_jobs"

    # ID of the tune job from the tuner API (primary key)
    id: Mapped[str] = mapped_column(db.String(36), primary_key=True)
    # ID of the experiment this job belongs to
    experiment_id: Mapped[str] = mapped_column(db.String(5), db.ForeignKey("experiments.id"))
    # Experiment-relative path to the .simulation.json manifest (job identity)
    simulation_path: Mapped[str] = mapped_column(db.String(255), nullable=False)
    # error message if job creation failed
    error_message: Mapped[str | None] = mapped_column(db.String(512), nullable=True)
    # creation time
    created_at: Mapped[datetime] = mapped_column(db.DateTime, default=lambda: datetime.now(UTC))
    # whether the job was stopped (preserves data but job is deleted from tuner)
    is_stopped: Mapped[bool] = mapped_column(db.Boolean, default=False, nullable=False)
    # preserved trials when job is stopped
    _preserved_trials: Mapped[list[dict] | None] = mapped_column("preserved_trials", JSON, nullable=True)

    # back-reference to the parent experiment
    experiment: Mapped["Experiment"] = relationship("Experiment", back_populates="tuner_jobs")

    @property
    def engine(self) -> Engine:
        """MD engine inferred from the parent experiment."""
        return self.experiment.engine

    @property
    def tuner_status(self) -> JobStatus:
        """Status of the job on the tuner."""
        return self._status().get("status", JobStatus.UNKNOWN)

    @property
    def trials(self) -> list[dict]:
        """Trial jobs with their statuses."""
        if self.is_stopped and self._preserved_trials:
            return self._preserved_trials
        return self._status().get("trials", [])

    def _status(self) -> dict:
        """
        Fetch tuner job status with caching and fallback on errors.

        Uses a TTL cache for normal operation and falls back to last known
        status on timeout or other errors to prevent breaking dependent code.

        Returns:
            Status dict with 'status' and 'trials' keys, or an empty dict if
            the job is stopped or no status is available.

        Raises:
            ValueError: If the tuner response is missing required fields.
        """
        if self.is_stopped:
            return {}

        cache_key = self.id

        # Return cached value if still fresh
        if cache_key in tuner_status_cache:
            return tuner_status_cache[cache_key]

        try:
            match self.engine:
                case Engine.GMX:
                    status = tuner.gmx_poll_status(self.id)
                case Engine.AMBER:
                    status = tuner.amber_poll_status(self.id)
                case _:
                    raise ValueError(f"Unknown engine: {self.engine}")

            if err_msg := status.get("error"):
                self.error_message = err_msg
                db.session.commit()

            # Validate response completeness
            if "status" not in status or "trials" not in status:
                raise ValueError(f"Incomplete status response from tuner for job {self.id}")

            # Update both caches on success
            tuner_status_cache[cache_key] = status
            tuner_last_known_status[cache_key] = status
            return status

        except TimeoutError:
            logger.warning(f"Timeout fetching tuner status for job {self.id}")
        except HTTPError as exc:
            # 404 means the tuner no longer has this job (reaped or restarted); stop re-polling.
            if exc.response is not None and exc.response.status_code == HTTPStatus.NOT_FOUND:
                logger.warning(f"Tuner job {self.id} not found on tuner; stopping")
                self.stop()
                db.session.commit()
            else:
                logger.exception(f"Error fetching tuner status for job {self.id}")
        except Exception:
            logger.exception(f"Error fetching tuner status for job {self.id}")

        # Return last known status if available, empty dict otherwise
        return tuner_last_known_status.get(cache_key, {})

    @classmethod
    def start(cls, experiment: Experiment, simulation_path: str, nsteps: int = 25000) -> "TunerJob":
        """
        Start a tuner job for the given experiment and simulation manifest.

        Launch files and ``extra_args`` are derived from the simulation JSON and
        passed to the tuner client; they are not persisted in the dashboard DB.

        Args:
            experiment: The parent experiment.
            simulation_path: Experiment-relative path to the ``.simulation.json``.
            nsteps: Number of steps for tuning runs (default: 25000, which is 50 ps).

        Returns:
            The created TunerJob instance.

        Raises:
            ValueError: If the engine is unknown.
        """
        simulation = get_simulation(experiment.id, simulation_path)
        validate_simulation_for_action(simulation, "tune")
        extra_args = simulation.get("extra_args", "")

        match experiment.engine:
            case Engine.GMX:
                tpr_path = resolve_simulation_role(experiment.id, simulation, "topology")
                response = tuner.gmx_submit(tpr_path, nsteps=nsteps, extra_args=extra_args)
            case Engine.AMBER:
                prmtop_path = resolve_simulation_role(experiment.id, simulation, "topology")
                inpcrd_path = resolve_simulation_role(experiment.id, simulation, "coordinates")
                mdin_path = resolve_simulation_role(experiment.id, simulation, "control")
                response = tuner.amber_submit(prmtop_path, inpcrd_path, mdin_path, nsteps=nsteps, extra_args=extra_args)
            case _:
                raise ValueError(f"Unknown engine: {experiment.engine}")

        job: TunerJob = cls(
            id=response["id"],
            experiment=experiment,
            simulation_path=simulation_path,
        )
        db.session.add(job)
        db.session.commit()

        mark_simulation_readonly(experiment.id, simulation_path)

        logger.info(
            f"Tuner job {response['id']} started for experiment {experiment.id} "
            f"with engine {experiment.engine} (simulation {simulation_path})"
        )
        return job

    def stop(self) -> None:
        """Stop the tuner job and preserve observed trials."""
        if self.is_stopped:
            return

        last = tuner_last_known_status.get(self.id, {})
        self._preserved_trials = [trial for trial in last.get("trials", []) if trial.get("performance") is not None]
        self.is_stopped = True

        try:
            match self.engine:
                case Engine.GMX:
                    tuner.gmx_delete_job(self.id)
                case Engine.AMBER:
                    tuner.amber_delete_job(self.id)
                case _:
                    pass
        except HTTPError:
            logger.exception(f"Failed to delete tuner job {self.id}")

        tuner_status_cache.clear()
        logger.info(f"Stopped tuner job {self.id}")

    def delete(self) -> None:
        """
        Delete the tuner job completely.

        If running, deletes from tuner API.
        If stopped, does nothing on tuner API.
        """
        if self.is_stopped:
            return

        try:
            match self.engine:
                case Engine.GMX:
                    tuner.gmx_delete_job(self.id)
                case Engine.AMBER:
                    tuner.amber_delete_job(self.id)
                case _:
                    pass  # Unknown engine, nothing to delete
        except HTTPError:
            logger.exception(f"Failed to delete tuner job {self.id}")
