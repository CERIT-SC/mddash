"""Archive/restore schemas."""

from typing import Literal, TypedDict

from core.schemas import ArchiveState
from pydantic import ConfigDict, with_config


@with_config(ConfigDict(extra="forbid"))
class ArchiveAttempt(TypedDict):
    """Accepted archive or restore."""

    attempt_id: str


@with_config(ConfigDict(extra="forbid"))
class ArchiveStatus(TypedDict):
    """Archive/restore state reconciled with live Jobs."""

    experiment_id: str
    archive_state: ArchiveState | None
    attempt_id: str | None
    direction: Literal["archive", "restore"] | None
    reason: str | None
