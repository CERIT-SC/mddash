import logging
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, ClassVar, Self

import anyio
import sqlalchemy as sa
from clients import mdrun
from core.cache import simulation_log_lines_cache, simulation_log_lines_lock, simulation_status_cache
from core.db import Base
from core.enums import Engine, JobStatus
from core.utils import count_lines
from sqlalchemy import select
from sqlalchemy.orm import Mapped, mapped_column, relationship, selectinload

if TYPE_CHECKING:
    from sqlalchemy import Select
    from sqlalchemy.ext.asyncio import AsyncSession

    from modules.experiments.models import Experiment


logger = logging.getLogger(__name__)


class SimulationJob(Base):
    """
    Base class for molecular dynamics simulation jobs using Joined Table Inheritance.

    Engine-specific subclasses (GromacsJob, AmberJob) add engine columns and log parsing.
    Remote status comes from `refresh_status()`; every other property is local (DB + files).
    """

    __tablename__ = "simulation_jobs"
    # One run per simulation; extend swaps the row in place so the PK stays the
    # current MDRun job; a second pod can never append to one trajectory.
    __table_args__ = (sa.UniqueConstraint("experiment_id", "simulation_path"),)
    __mapper_args__ = {"polymorphic_on": "engine"}  # ruff:ignore[mutable-class-default]  # SQLAlchemy declares it an instance attribute

    # MDRun API path segment of this engine (`/jobs/<engine>/...`)
    MDRUN_ENGINE: ClassVar[str]

    # ID of the job inside the database
    id: Mapped[str] = mapped_column(sa.String(36), primary_key=True)
    # ID of the experiment this job belongs to
    experiment_id: Mapped[str] = mapped_column(sa.String(5), sa.ForeignKey("experiments.id"))
    # Experiment-relative path to the .simulation.json manifest (job identity)
    simulation_path: Mapped[str] = mapped_column(sa.String(255), nullable=False)
    # Creation time
    created_at: Mapped[datetime] = mapped_column(sa.DateTime, default=lambda: datetime.now(UTC))
    # Engine discriminator for JTI
    engine: Mapped[Engine] = mapped_column(sa.Enum(Engine), nullable=False)

    # Number of MPI processes
    np: Mapped[int] = mapped_column(sa.Integer, nullable=False)
    # Number of OpenMP threads per MPI rank
    ntomp: Mapped[int] = mapped_column(sa.Integer, nullable=False)

    # Unix timestamp when the job started
    _start_timestamp: Mapped[int | None] = mapped_column("start_timestamp", sa.Integer, nullable=True)
    # Unix timestamp when the job finished
    _finish_timestamp: Mapped[int | None] = mapped_column("finish_timestamp", sa.Integer, nullable=True)
    # Total steps of the job
    _nsteps: Mapped[int | None] = mapped_column("nsteps", sa.Integer, nullable=True)
    # Performance (ns/day)
    _performance: Mapped[float | None] = mapped_column("performance", sa.Float, nullable=True)
    # Last successfully-fetched non-UNKNOWN status (fallback when MDRun API is unavailable)
    _last_known_status: Mapped[JobStatus | None] = mapped_column("last_known_status", sa.Enum(JobStatus), nullable=True)

    # Back-reference to the parent experiment
    # Never lazy-loads (async); queries for jobs alone load it via `query()`.
    experiment: Mapped["Experiment"] = relationship("Experiment", back_populates="simulation_jobs", lazy="raise_on_sql")

    # Transient: status fetched by refresh_status() for this request
    _fetched_status: JobStatus | None = None

    @classmethod
    def query(cls) -> "Select[tuple[Self]]":
        """Select rows of this job type together with their experiments."""
        return select(cls).options(selectinload(cls.experiment))

    @classmethod
    async def get(cls, session: "AsyncSession", experiment_id: str, simulation_path: str) -> Self | None:
        """Return the simulation's single run row (unique per experiment and path), or None."""
        stmt = cls.query().filter_by(experiment_id=experiment_id, simulation_path=simulation_path)
        return (await session.execute(stmt)).scalars().first()

    @classmethod
    async def remove(cls, session: "AsyncSession", experiment_id: str, simulation_path: str) -> Self | None:
        """
        Delete the simulation's run: its MDRun job, DB row, and result files.

        Returns:
            The deleted row, or None when the simulation never ran.
        """
        job = await cls.get(session, experiment_id, simulation_path)
        if job is None:
            return None
        await job.delete()
        await session.delete(job)
        await session.commit()
        return job

    async def _mdrun_get(self) -> dict:
        raise NotImplementedError

    async def _mdrun_delete(self) -> None:
        raise NotImplementedError

    async def refresh_status(self) -> JobStatus:
        """Fetch the MDRun status (short TTL cache); terminal states never change, so they skip the fetch."""
        if self._last_known_status is not None and self._last_known_status.is_terminal:
            self._fetched_status = self._last_known_status
            return self._fetched_status

        try:
            fetched = simulation_status_cache.get(self.id)
            if fetched is None:
                fetched = JobStatus.from_string((await self._mdrun_get())["status"])
                simulation_status_cache[self.id] = fetched
            if fetched not in {self._last_known_status, JobStatus.UNKNOWN}:
                self._last_known_status = fetched
        except Exception:
            logger.exception(f"Error fetching job status for job {self.id}")
            fetched = self._last_known_status or JobStatus.UNKNOWN

        self._fetched_status = fetched
        return fetched

    @property
    def status(self) -> JobStatus:
        """
        Current status of the MDRun job, as of the last `refresh_status()`.

        Raises:
            RuntimeError: If a non-terminal job was not refreshed in this request.
        """
        if self._last_known_status is not None and self._last_known_status.is_terminal:
            return self._last_known_status
        if self._fetched_status is None:
            raise RuntimeError(f"Status of job {self.id} read before refresh_status()")
        return self._fetched_status

    @property
    def is_live(self) -> bool:
        """The job may still advance without user action."""
        return self.status.is_live

    @property
    def _archived(self) -> bool:
        """Parent experiment is archived: files are gone, so derived values serve persisted columns."""
        return self.experiment is not None and self.experiment.archived_at is not None

    @property
    def log_lines(self) -> dict[str, int | None]:
        """
        Line count per log stream, keyed by the log endpoint's ``type`` values.

        Lets clients size logs (line-count badges) without downloading them;
        None while a stream's file does not exist yet. The counts ride the job
        payload, so they stay fresh on the existing status polls.
        """
        if self._archived:
            return {}
        # Keyed by job id: ORM instances are rebuilt per request.
        with simulation_log_lines_lock:
            cached = simulation_log_lines_cache.get(self.id)
        if cached is not None:
            return cached
        counts = {name: count_lines(path) for name, path in self._log_files().items()}
        with simulation_log_lines_lock:
            simulation_log_lines_cache[self.id] = counts
        return counts

    def _log_files(self) -> dict[str, Path]:
        """Log streams keyed by the log endpoint's ``type`` values (engine log key is ``gmx`` or ``mdout``)."""
        raise NotImplementedError

    @property
    def nsteps(self) -> int | None:
        """Total steps of the run."""
        raise NotImplementedError

    @property
    def estimated_time(self) -> int | None:
        """Estimated seconds until completion."""
        raise NotImplementedError

    @property
    def nsteps_done(self) -> int | None:
        """Number of steps completed so far (absolute trajectory step)."""
        if self._archived:
            return self._nsteps if self._performance else None

        # Only a genuinely finished run may shortcut to its target: a stopped run
        # prints a performance trailer too, so cached performance proves nothing.
        if self._performance and self.status == JobStatus.FINISHED:
            return self._nsteps

        return self._parse_nsteps_done()

    @property
    def start_timestamp(self) -> int | None:
        """Unix timestamp when the job started."""
        if self._archived or self._start_timestamp:
            return self._start_timestamp

        if val := self._parse_start_timestamp():
            self._start_timestamp = val

        return self._start_timestamp

    @property
    def finish_timestamp(self) -> int | None:
        """Unix timestamp when the job finished."""
        if self._archived or self._finish_timestamp:
            return self._finish_timestamp

        if self.status != JobStatus.FINISHED:
            return None

        if val := self._parse_finish_timestamp():
            self._finish_timestamp = val

        return self._finish_timestamp

    @property
    def performance(self) -> float | None:
        """Performance of the job in ns/day (only once the run itself finished)."""
        if self._archived or self._performance:
            return self._performance

        # Live/stopped runs would inherit the previous run's Performance line from the appended log.
        if self.status != JobStatus.FINISHED:
            return None

        if val := self._parse_performance():
            self._performance = val

        return self._performance

    def _parse_nsteps_done(self) -> int | None:
        raise NotImplementedError

    def _parse_performance(self) -> float | None:
        raise NotImplementedError

    def _parse_start_timestamp(self) -> int | None:
        raise NotImplementedError

    def _parse_finish_timestamp(self) -> int | None:
        raise NotImplementedError

    async def delete(self) -> None:
        """Delete the MDRun job and this run's result files (the caller deletes the row)."""
        await self._mdrun_delete()
        await anyio.to_thread.run_sync(self._cleanup_files)

    async def stop(self) -> None:
        """
        Stop the job gracefully, preserving all data and the DB row (row later extends, GMX, or analyzes as-is).

        Outcome re-read after deletion: a run that finishes first stays FINISHED, not STOPPED.
        """
        await mdrun.stop_job(self.id, self.MDRUN_ENGINE)
        try:
            status = JobStatus.from_string((await self._mdrun_get())["status"])
        except Exception:
            logger.exception(f"Could not re-read status of job {self.id} after stop; assuming STOPPED")
            status = JobStatus.STOPPED
        self._last_known_status = status
        self._fetched_status = status
        simulation_status_cache.pop(self.id, None)

    def _cleanup_files(self) -> None:
        """Remove engine-specific result files of this run (subclasses override)."""
