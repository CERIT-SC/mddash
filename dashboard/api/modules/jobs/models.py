import logging
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, ClassVar, Self

import sqlalchemy as sa
from core.cache import simulation_log_lines_cache, simulation_log_lines_lock
from core.db import Base
from core.enums import Engine, JobStatus
from core.errors import BadRequest, Forbidden, InternalServerError, NotFound, UnprocessableEntity
from core.utils import count_lines, tail
from sqlalchemy import select
from sqlalchemy.orm import Mapped, mapped_column, relationship, selectinload

from modules.jobs.status import RecordedStatus

if TYPE_CHECKING:
    from sqlalchemy import Select

    from modules.experiments.models import Experiment


logger = logging.getLogger(__name__)


class SimulationJob(RecordedStatus, Base):
    """
    Base class for molecular dynamics simulation jobs using Joined Table Inheritance.

    Engine-specific subclasses (GromacsJob, AmberJob) add engine columns and log parsing.
    Remote status comes from `RunService.refresh_status()`; every other property is local (DB + files).
    """

    __tablename__ = "simulation_jobs"
    # One run per simulation; extend swaps the row in place so the PK stays the
    # current MDRun job; a second pod can never append to one trajectory.
    # A losing concurrent extend deletes a row the winner already replaced; the unique
    # constraint fails its insert, so the missed DELETE is expected (confirm_deleted_rows).
    __table_args__ = (sa.UniqueConstraint("experiment_id", "simulation_path"),)
    __mapper_args__ = {"polymorphic_on": "engine", "confirm_deleted_rows": False}  # ruff:ignore[mutable-class-default]  # SQLAlchemy declares it an instance attribute

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

    # Back-reference to the parent experiment
    # Never lazy-loads (async); queries for jobs alone load it via `query()`.
    experiment: Mapped["Experiment"] = relationship("Experiment", back_populates="simulation_jobs", lazy="raise_on_sql")

    @classmethod
    def query(cls) -> "Select[tuple[Self]]":
        """Select rows of this job type together with their experiments."""
        return select(cls).options(selectinload(cls.experiment))

    def mark_status(self, status: JobStatus) -> None:
        """Persist a status MDRun reported for an action (stop)."""
        self._last_known_status = status
        self._fetched_status = status

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

    def _readable_logs(self) -> dict[str, Path]:
        """Files the log endpoint serves, keyed by its ``type`` values."""
        return self._log_files()

    def get_log(self, log_type: str, tail_lines: int | None = None) -> str:
        """
        Read one of the run's logs, or its last `tail_lines` lines (sync file I/O).

        Raises:
            BadRequest: If the log type is not one this engine writes.
        """
        logs = self._readable_logs()
        if (log_file := logs.get(log_type)) is None:
            allowed = ", ".join(f"'{name}'" for name in logs)
            raise BadRequest(f"Invalid log type '{log_type}'. Use one of {allowed}.")
        try:
            if tail_lines:
                return tail(log_file, tail_lines)
            return log_file.read_text()
        except FileNotFoundError:
            raise NotFound(f"Log file not found: {log_file.name}") from None
        except PermissionError:
            raise Forbidden(f"Permission denied accessing log file: {log_file.name}") from None
        except UnicodeDecodeError:
            raise UnprocessableEntity(f"Unable to decode log file: {log_file.name}") from None
        except OSError as e:
            raise InternalServerError("System error reading log file.") from e

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

    def cleanup_files(self) -> None:
        """Remove engine-specific result files of this run (subclasses override)."""
