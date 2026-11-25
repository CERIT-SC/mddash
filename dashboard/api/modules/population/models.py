from datetime import UTC, datetime
from typing import TYPE_CHECKING

import sqlalchemy as sa
from core.db import Base
from core.enums import Engine, PopulationPhase, PopulationStatus
from sqlalchemy.orm import Mapped, mapped_column, relationship

if TYPE_CHECKING:
    from modules.experiments.models import Experiment


class PopulationOperation(Base):
    """
    A Datahugger-NG population lifecycle owned by its provisional Experiment.

    The Experiment and its Notebook exist as soon as the worker is accepted, so
    progress, failure, and cancellation are visible before the dataset is merged.
    Only the Dashboard API writes this table; the worker writes receipts.
    """

    __tablename__ = "population_operations"

    # Unique operation identifier (not a directory; staging lives under .cache)
    id: Mapped[str] = mapped_column(sa.String(16), primary_key=True)
    # Owning provisional experiment (row exists from submission, not only on success)
    experiment_id: Mapped[str] = mapped_column(
        sa.String(5), sa.ForeignKey("experiments.id", ondelete="CASCADE"), nullable=False, unique=True, index=True
    )
    # Experiment name captured at submission (creation metadata, non-secret)
    name: Mapped[str] = mapped_column(sa.String(255), nullable=False)
    # Submitted public repository URL; becomes the experiment's repo provenance on success
    repo_url: Mapped[str] = mapped_column(sa.String(512), nullable=False)
    notebooks_repo: Mapped[str | None] = mapped_column(sa.String(512), nullable=True)
    module_name: Mapped[str | None] = mapped_column(sa.String(255), nullable=True)
    module_category: Mapped[str | None] = mapped_column(sa.String(32), nullable=True)
    engine: Mapped[Engine] = mapped_column(sa.Enum(Engine), nullable=False, default=Engine.GMX)
    # Deterministic one-shot worker Job name
    job_name: Mapped[str] = mapped_column(sa.String(63), nullable=False)
    status: Mapped[PopulationStatus] = mapped_column(
        sa.Enum(PopulationStatus), nullable=False, default=PopulationStatus.queued
    )
    phase: Mapped[PopulationPhase] = mapped_column(
        sa.Enum(PopulationPhase), nullable=False, default=PopulationPhase.starting
    )
    # Measured staging progress: files/bytes that exist, never completed or validated files.
    files_present: Mapped[int] = mapped_column(sa.Integer, nullable=False, default=0)
    files_total: Mapped[int | None] = mapped_column(sa.Integer, nullable=True)
    bytes_present: Mapped[int] = mapped_column(sa.Integer, nullable=False, default=0)
    # Summed only when every selected downloadable entry has a known size.
    bytes_total: Mapped[int | None] = mapped_column(sa.Integer, nullable=True)
    # Dataset entries renamed at merge because the notebooks already used the name
    renamed_paths: Mapped[list[str] | None] = mapped_column(sa.JSON, nullable=True)
    # Stable, user-safe failure text; raw native details stay in server logs
    error: Mapped[str | None] = mapped_column(sa.String(512), nullable=True)
    created_at: Mapped[datetime] = mapped_column(sa.DateTime, default=lambda: datetime.now(UTC))
    updated_at: Mapped[datetime] = mapped_column(
        sa.DateTime,
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
    )
    finished_at: Mapped[datetime | None] = mapped_column(sa.DateTime, nullable=True)

    experiment: Mapped["Experiment"] = relationship(back_populates="population", lazy="raise_on_sql")

    @property
    def operation_id(self) -> str:
        """Alias for the API contract (the operation's primary key)."""
        return self.id

    @property
    def byte_percentage(self) -> float | None:
        """Determinable only from a known positive total; presentation clamps to 100%."""
        if not self.bytes_total:
            return None
        return min(100.0, (self.bytes_present / self.bytes_total) * 100)
