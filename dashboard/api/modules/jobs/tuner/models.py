import logging
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Self

import sqlalchemy as sa
from core.db import Base
from core.enums import Engine, JobStatus
from sqlalchemy import JSON, Select, select
from sqlalchemy.orm import Mapped, mapped_column, relationship, selectinload

if TYPE_CHECKING:
    from modules.experiments.models import Experiment

logger = logging.getLogger(__name__)


class TunerJob(Base):
    """Tuner job for optimizing MD simulation parameters (GROMACS or AMBER)."""

    __tablename__ = "tuner_jobs"

    # ID of the tune job from the tuner API (primary key)
    id: Mapped[str] = mapped_column(sa.String(36), primary_key=True)
    # ID of the experiment this job belongs to
    experiment_id: Mapped[str] = mapped_column(sa.String(5), sa.ForeignKey("experiments.id"))
    # Experiment-relative path to the .simulation.json manifest (job identity)
    simulation_path: Mapped[str] = mapped_column(sa.String(255), nullable=False)
    # error message if job creation failed
    error_message: Mapped[str | None] = mapped_column(sa.String(512), nullable=True)
    # creation time
    created_at: Mapped[datetime] = mapped_column(sa.DateTime, default=lambda: datetime.now(UTC))
    # number of steps each tuning trial runs (always caller-supplied; no default, fail fast)
    nsteps: Mapped[int] = mapped_column(sa.Integer, nullable=False)
    # whether the job was stopped (preserves data but job is deleted from tuner)
    is_stopped: Mapped[bool] = mapped_column(sa.Boolean, default=False, nullable=False)
    # preserved trials when job is stopped
    _preserved_trials: Mapped[list[dict] | None] = mapped_column("preserved_trials", JSON, nullable=True)

    # back-reference to the parent experiment
    # Never lazy-loads (async); queries for jobs alone load it via `query()`.
    experiment: Mapped["Experiment"] = relationship("Experiment", back_populates="tuner_jobs", lazy="raise_on_sql")

    # Transient: tuner status payload fetched by TunerService.refresh() for this request
    _status_data: dict | None = None

    @classmethod
    def query(cls) -> "Select[tuple[Self]]":
        """Select tuner jobs together with their experiments."""
        return select(cls).options(selectinload(cls.experiment))

    @property
    def engine(self) -> Engine:
        """MD engine inferred from the parent experiment."""
        return self.experiment.engine

    @property
    def tuner_status(self) -> JobStatus:
        """Status of the job on the tuner; the status dict carries raw JSON strings."""
        return JobStatus.parse(self._status().get("status", JobStatus.UNKNOWN))

    @property
    def is_live(self) -> bool:
        """A stopped job is terminal even though its status reads UNKNOWN."""
        return not self.is_stopped and self.tuner_status.is_live

    @property
    def sim_length_ns(self) -> float | None:
        """Full production simulation length (ns) reported by the tuner."""
        return self._status().get("sim_length_ns")

    @property
    def trials(self) -> list[dict]:
        """Trial jobs with their statuses."""
        if self.is_stopped and self._preserved_trials:
            return self._preserved_trials
        return self._status().get("trials", [])

    def _status(self) -> dict:
        """
        Tuner status as of the last `TunerService.refresh()`; empty once stopped.

        Raises:
            RuntimeError: If a running job was not refreshed in this request.
        """
        if self.is_stopped:
            return {}
        if self._status_data is None:
            raise RuntimeError(f"Status of tuner job {self.id} read before TunerService.refresh()")
        return self._status_data

    def record_status(self, status: dict) -> None:
        """Store the tuner status payload read for this request."""
        self._status_data = status

    def preserve_trials(self, last_status: dict) -> None:
        """Mark the job stopped, keeping the trials that produced a performance (the tuner job is deleted)."""
        self._preserved_trials = [
            trial for trial in last_status.get("trials", []) if trial.get("performance") is not None
        ]
        self.is_stopped = True
