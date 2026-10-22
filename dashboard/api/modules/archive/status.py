"""Durable archive status document (contract between Dashboard API and archive worker)."""

from __future__ import annotations

import contextlib
import logging
from dataclasses import asdict, dataclass
from enum import Enum
from typing import TYPE_CHECKING, Any

from core.worker_jobs import read_status_doc, write_status_doc

if TYPE_CHECKING:
    from pathlib import Path

logger = logging.getLogger(__name__)

STATUS_FILENAME = ".archive-status.json"


class ArchiveState(str, Enum):
    """Archive states persisted in the status document."""

    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class ArchiveDirection(str, Enum):
    """Status document directions."""

    ARCHIVE = "archive"
    RESTORE = "restore"


@dataclass
class ArchiveStatus:
    """Only fields that are read back are stored; experiment_id is implicit from the file path."""

    attempt_id: str
    state: str
    direction: str
    reason: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """Serialise to a JSON-compatible dict."""
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ArchiveStatus:
        """Tolerate missing fields (status files from older attempts may lack newer keys)."""
        return cls(
            attempt_id=data.get("attempt_id", ""),
            state=data.get("state", ""),
            direction=data.get("direction", ""),
            reason=data.get("reason"),
        )


def status_path(experiment_id: str, data_dir: Path) -> Path:
    """Status file location: inside the experiment dir (deleted with it on archive)."""
    return data_dir / experiment_id / STATUS_FILENAME


def read_status(experiment_id: str, data_dir: Path) -> ArchiveStatus | None:
    """Return None if the file does not exist or is corrupt."""
    data = read_status_doc(status_path(experiment_id, data_dir))
    return None if data is None else ArchiveStatus.from_dict(data)


def write_status(status: ArchiveStatus, experiment_id: str, data_dir: Path) -> None:
    """Atomic write via temp file, fsync, rename."""
    write_status_doc(status_path(experiment_id, data_dir), status.to_dict())


def create_queued_status(attempt_id: str, direction: str) -> ArchiveStatus:
    """Build the initial status the API writes at Job submission."""
    return ArchiveStatus(attempt_id=attempt_id, state=ArchiveState.QUEUED.value, direction=direction)


def delete_status(experiment_id: str, data_dir: Path) -> None:
    """Best-effort removal of the status doc, e.g. when Job submission fails after writing it."""
    with contextlib.suppress(OSError):
        status_path(experiment_id, data_dir).unlink()
