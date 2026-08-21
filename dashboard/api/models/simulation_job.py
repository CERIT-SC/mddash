import logging
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any, ClassVar

from cache import simulation_log_lines_cache, simulation_status_cache
from cachetools import cached
from clients import mdrun
from enums import Engine, JobStatus
from extensions import db
from sqlalchemy.orm import Mapped, mapped_column, relationship
from utils import count_lines

if TYPE_CHECKING:
    from .experiment import Experiment


logger = logging.getLogger(__name__)


class SimulationJob(db.Model):  # type: ignore
    """
    Base class for molecular dynamics simulation jobs using Joined Table Inheritance.

    Engine-specific subclasses (GromacsJob, AmberJob) inherit from this base model
    and provide additional engine-specific columns and methods.
    """

    __tablename__ = "simulation_jobs"
    __mapper_args__: ClassVar[dict[str, Any]] = {"polymorphic_on": "engine"}

    # ID of the job inside the database
    id: Mapped[str] = mapped_column(db.String(36), primary_key=True)
    # ID of the experiment this job belongs to
    experiment_id: Mapped[str] = mapped_column(db.String(5), db.ForeignKey("experiments.id"))
    # Experiment-relative path to the .simulation.json manifest (job identity)
    simulation_path: Mapped[str] = mapped_column(db.String(255), nullable=False)
    # Creation time
    created_at: Mapped[datetime] = mapped_column(db.DateTime, default=lambda: datetime.now(UTC))
    # Engine discriminator for JTI
    engine: Mapped[Engine] = mapped_column(db.Enum(Engine), nullable=False)

    # Number of MPI processes
    np: Mapped[int] = mapped_column(db.Integer, nullable=False)
    # Number of OpenMP threads per MPI rank
    ntomp: Mapped[int] = mapped_column(db.Integer, nullable=False)

    # Unix timestamp when the job started
    _start_timestamp: Mapped[int | None] = mapped_column("start_timestamp", db.Integer, nullable=True)
    # Unix timestamp when the job finished
    _finish_timestamp: Mapped[int | None] = mapped_column("finish_timestamp", db.Integer, nullable=True)
    # Total steps of the job
    _nsteps: Mapped[int | None] = mapped_column("nsteps", db.Integer, nullable=True)
    # Performance (ns/day)
    _performance: Mapped[float | None] = mapped_column("performance", db.Float, nullable=True)
    # Last successfully-fetched non-UNKNOWN status (fallback when MDRun API is unavailable)
    _last_known_status: Mapped[JobStatus | None] = mapped_column("last_known_status", db.Enum(JobStatus), nullable=True)

    # Back-reference to the parent experiment
    experiment: Mapped["Experiment"] = relationship("Experiment", back_populates="simulation_jobs")

    @property
    @cached(cache=simulation_status_cache)
    def status(self) -> JobStatus:
        """
        Current status of the Kubernetes job.

        Dispatches to the appropriate mdrun client method based on engine type.
        Uses a short TTL cache to reduce API calls.

        Returns:
            The current JobStatus of the simulation.
        """
        # Terminal states never change — skip fetch
        if self._last_known_status is not None and self._last_known_status in {
            JobStatus.FINISHED,
            JobStatus.ERROR,
        }:
            return self._last_known_status

        try:
            match self.engine:
                case Engine.GMX:
                    fetched = JobStatus.from_string(mdrun.get_gmx_job(self.id)["status"])
                case Engine.AMBER:
                    fetched = JobStatus.from_string(mdrun.get_amber_job(self.id)["status"])

            if fetched not in {self._last_known_status, JobStatus.UNKNOWN}:
                self._last_known_status = fetched
                db.session.commit()
            return fetched
        except Exception:
            logger.exception(f"Error fetching job status for job {self.id}")
            if self._last_known_status:
                return self._last_known_status
            return JobStatus.UNKNOWN

    @property
    @cached(cache=simulation_log_lines_cache)
    def log_lines(self) -> dict[str, int | None]:
        """
        Line count per log stream, keyed by the log endpoint's ``type`` values.

        Lets clients size logs (line-count badges) without downloading them;
        None while a stream's file does not exist yet. The counts ride the job
        payload, so they stay fresh on the existing status polls.
        """
        return {name: count_lines(path) for name, path in self._log_files().items()}

    def _log_files(self) -> dict[str, Path]:
        """
        Log streams of this job, keyed by the log endpoint's ``type`` values.

        Engine-specific; the engine log key is ``gmx`` or ``mdout``.
        """
        raise NotImplementedError

    def delete(self) -> None:
        """
        Delete the simulation job and its associated resources.

        Dispatches to the appropriate mdrun client method based on engine type,
        then cleans up local files.
        """
        match self.engine:
            case Engine.GMX:
                mdrun.delete_gmx_job(self.id)
            case Engine.AMBER:
                mdrun.delete_amber_job(self.id)

        self._cleanup_files()

    def _cleanup_files(self) -> None:
        """
        Clean up files associated with this job.

        Override in subclasses to clean up engine-specific files.
        Base implementation does nothing.
        """
        pass
