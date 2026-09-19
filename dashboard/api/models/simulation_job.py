import logging
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any, ClassVar, Self

from cache import simulation_log_lines_cache, simulation_status_cache
from cachetools import cached
from clients import mdrun
from enums import Engine, JobStatus
from extensions import db
from sqlalchemy import Index, text
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
    # At most one live segment per simulation: rows are born PENDING and a second
    # concurrent extension violates this index instead of spawning two pods that
    # append to one trajectory. NULL (never-yet-polled legacy rows) is deliberately
    # excluded — status fetches converge them before any extend can insert.
    __table_args__ = (
        Index(
            "uq_simulation_jobs_live_segment",
            "experiment_id",
            "simulation_path",
            unique=True,
            sqlite_where=text("last_known_status IN ('PENDING', 'RUNNING', 'UNKNOWN')"),
        ),
    )
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
    # Frozen progress for terminal segments (set by extend so appended log
    # can't overwrite this row's display). Null while live; parsers fill in.
    _nsteps_done: Mapped[int | None] = mapped_column("nsteps_done", db.Integer, nullable=True)
    # Last successfully-fetched non-UNKNOWN status (fallback when MDRun API is unavailable)
    _last_known_status: Mapped[JobStatus | None] = mapped_column("last_known_status", db.Enum(JobStatus), nullable=True)

    # Back-reference to the parent experiment
    experiment: Mapped["Experiment"] = relationship("Experiment", back_populates="simulation_jobs")

    @classmethod
    def latest_for(cls, experiment_id: str, simulation_path: str) -> Self | None:
        """Latest (most recently created) segment of the simulation's run history, or None."""
        return (
            cls.query
            .filter_by(experiment_id=experiment_id, simulation_path=simulation_path)
            .order_by(cls.created_at.desc())
            .first()
        )

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
        if self._last_known_status is not None and self._last_known_status.is_terminal:
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
    def is_live(self) -> bool:
        """Non-terminal states — the job may still advance without user action."""
        return self.status.is_live

    # Key by job id: ORM instances are rebuilt per request, so the default
    # instance-hash key would never hit and every dump would stream whole logs.
    @property
    @cached(cache=simulation_log_lines_cache, key=lambda job: job.id)
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

    @property
    def nsteps_done(self) -> int | None:
        """Number of steps completed so far (persisted for terminal rows once frozen)."""
        if self._nsteps_done is not None:
            return self._nsteps_done

        # Only a genuinely finished run may shortcut to its target: a stopped run
        # prints a performance trailer too, so cached performance proves nothing.
        if self._performance and self.status == JobStatus.FINISHED:
            return self._nsteps

        return self._parse_nsteps_done()

    @nsteps_done.setter
    def nsteps_done(self, value: int) -> None:
        """Freeze a terminal segment's progress (extend flow) so later appends can't rewrite it."""
        self._nsteps_done = value

    @property
    def start_timestamp(self) -> int | None:
        """Unix timestamp when the job started."""
        if self._start_timestamp:
            return self._start_timestamp

        if val := self._parse_start_timestamp():
            self._start_timestamp = val
            db.session.commit()

        return self._start_timestamp

    @property
    def finish_timestamp(self) -> int | None:
        """Unix timestamp when the job finished."""
        if self._finish_timestamp:
            return self._finish_timestamp

        if self.status != JobStatus.FINISHED:
            return None

        if val := self._parse_finish_timestamp():
            self._finish_timestamp = val
            db.session.commit()

        return self._finish_timestamp

    @property
    def performance(self) -> float | None:
        """Performance of the job in ns/day (only once the run itself finished)."""
        if self._performance:
            return self._performance

        # Live/stopped segments would inherit the previous segment's Performance line from the appended log.
        if self.status != JobStatus.FINISHED:
            return None

        if val := self._parse_performance():
            self._performance = val
            db.session.commit()

        return self._performance

    def _parse_nsteps_done(self) -> int | None:
        raise NotImplementedError

    def _parse_performance(self) -> float | None:
        raise NotImplementedError

    def _parse_start_timestamp(self) -> int | None:
        raise NotImplementedError

    def _parse_finish_timestamp(self) -> int | None:
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

    def stop(self) -> None:
        """
        Stop the job gracefully, preserving all data and the DB row (row later extends, GMX, or analyzes as-is).

        Outcome re-read after deletion: a run that finishes first stays FINISHED, not STOPPED.
        """
        match self.engine:
            case Engine.GMX:
                mdrun.stop_job(self.id, "gmx")
                get = mdrun.get_gmx_job
            case Engine.AMBER:
                mdrun.stop_job(self.id, "amber")
                get = mdrun.get_amber_job

        try:
            self._last_known_status = JobStatus.from_string(get(self.id)["status"])
        except Exception:
            logger.exception(f"Could not re-read status of job {self.id} after stop; assuming STOPPED")
            self._last_known_status = JobStatus.STOPPED
        db.session.commit()

    def _cleanup_files(self) -> None:
        """
        Clean up files associated with this job.

        Override in subclasses to clean up engine-specific files.
        Base implementation does nothing.
        """
        pass
