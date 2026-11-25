"""Headless setup run schemas."""

from datetime import datetime
from enum import StrEnum
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field

from modules.notebooks.schemas import Tier

DEFAULT_SETUP_NOTEBOOK = "setup.ipynb"


class SetupState(StrEnum):
    """Lifecycle of a headless setup run."""

    STARTING = "starting"
    RUNNING = "running"
    DONE = "done"
    STOPPED = "stopped"
    FAILED = "failed"


class SetupRunError(BaseModel):
    """Why a setup run failed: the notebook's own error, or a friendly infrastructure message."""

    step: Annotated[int | None, Field(description="1-based step the run stopped at")] = None
    title: str | None = None
    message: str
    solution: str | None = None


class SetupRun(BaseModel):
    """A headless setup run, reconciled from its Kubernetes Job and the executor's status doc."""

    notebook: str
    state: SetupState
    waiting: Annotated[bool, Field(description="Starting, but the pod can't be scheduled yet")] = False
    step: Annotated[int, Field(description="1-based step in progress or reached; 0 before the first")] = 0
    total: int | None = None
    title: str | None = None
    error: SetupRunError | None = None
    manifests: Annotated[list[str], Field(description="Experiment-relative manifests the run wrote")] = []
    started_at: datetime | None = None
    finished_at: datetime | None = None


class StartSetupRequest(BaseModel):
    """Setup run options."""

    model_config = ConfigDict(extra="forbid")

    notebook: Annotated[str, Field(min_length=1, description="Experiment-relative notebook")] = DEFAULT_SETUP_NOTEBOOK
    tier: Tier | None = None
    gpu: bool = False
