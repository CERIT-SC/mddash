from datetime import UTC, datetime

import sqlalchemy as sa
from core.db import Base
from core.enums import Engine, PopulationStatus
from sqlalchemy.orm import Mapped, mapped_column


class PopulationOperation(Base):
    """
    A one-shot Datahugger-NG population of a reserved experiment directory.

    Its lifetime is independent of the Experiment row: a failed population
    leaves no experiment behind, and terminal rows are pruned after 24 hours.
    Only the Dashboard API writes this table; the worker writes receipts.
    """

    __tablename__ = "population_operations"

    # Unique operation identifier (not a directory; staging lives under .cache)
    id: Mapped[str] = mapped_column(sa.String(16), primary_key=True)
    # Reserved experiment directory the population merges into (row exists only on success)
    experiment_id: Mapped[str] = mapped_column(sa.String(5), nullable=False)
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
    # Stable, user-safe failure text; raw native details stay in server logs
    error: Mapped[str | None] = mapped_column(sa.String(512), nullable=True)
    created_at: Mapped[datetime] = mapped_column(sa.DateTime, default=lambda: datetime.now(UTC))
    updated_at: Mapped[datetime] = mapped_column(
        sa.DateTime,
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
    )
    finished_at: Mapped[datetime | None] = mapped_column(sa.DateTime, nullable=True)
