import logging
from typing import TYPE_CHECKING
from uuid import uuid4

import sqlalchemy as sa
from core.config import PREFIX
from core.db import Base
from core.enums import NotebookTier, PodStatus
from sqlalchemy.orm import Mapped, mapped_column, relationship

if TYPE_CHECKING:
    from datetime import datetime

    from modules.experiments.models import Experiment


logger = logging.getLogger(__name__)


class Notebook(Base):
    """JupyterLab notebook instance for experiment setup."""

    __tablename__ = "notebooks"

    # ID of the notebook inside the database
    id: Mapped[int] = mapped_column(sa.Integer, primary_key=True)
    # ID of the experiment this notebook belongs to
    experiment_id: Mapped[str] = mapped_column(sa.String(5), sa.ForeignKey("experiments.id"))
    # token for accessing jupyter notebook
    token: Mapped[str] = mapped_column(sa.String(36), nullable=False, default=lambda: str(uuid4()))
    # resource tier (1x, 2x, 4x); NULL for notebooks created before tiers were introduced
    tier: Mapped[NotebookTier | None] = mapped_column(sa.Enum(NotebookTier), nullable=True)
    # whether GPU is attached to the notebook container
    gpu: Mapped[bool] = mapped_column(sa.Boolean, default=False, server_default=sa.text("0"))

    # back-reference to the parent experiment
    # Never lazy-loads (async); notebooks are always reached through their experiment.
    experiment: Mapped["Experiment"] = relationship("Experiment", back_populates="notebook", lazy="raise_on_sql")

    # Transient: (status, start time) from one K8s read by NotebookService.refresh()
    _pod_info: "tuple[PodStatus, datetime | None] | None" = None

    @property
    def path(self) -> str:
        """Path to access the notebook via Caddy."""
        return f"{PREFIX}/notebook/{self.experiment_id}/?token={self.token}"

    @property
    def pod_name(self) -> str:
        """Name of the notebook pod."""
        return f"notebook-{self.experiment_id}"

    def record_pod(self, info: "tuple[PodStatus, datetime | None]") -> None:
        """Store the pod's (status, start time) read for this request."""
        self._pod_info = info

    @property
    def refreshed(self) -> bool:
        """Whether the pod was read in this request."""
        return self._pod_info is not None

    def _pod(self) -> "tuple[PodStatus, datetime | None]":
        if self._pod_info is None:
            raise RuntimeError(f"Notebook {self.experiment_id} pod read before NotebookService.refresh()")
        return self._pod_info

    @property
    def status(self) -> PodStatus:
        """The status of the notebook pod."""
        return self._pod()[0]

    @property
    def started_at(self) -> "datetime | None":
        """When the notebook pod was started (None while the pod is absent)."""
        return self._pod()[1]
