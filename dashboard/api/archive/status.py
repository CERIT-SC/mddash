"""Durable archive status document (contract between Dashboard API and archive worker)."""

from __future__ import annotations

import contextlib
import json
import logging
import os
import tempfile
from dataclasses import asdict, dataclass
from enum import Enum
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

STATUS_FILENAME = ".archive-status.json"
STATUS_TMP_SUFFIX = ".tmp"


class ArchiveState(str, Enum):
    """Archive states persisted in the status document."""

    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"

    @classmethod
    def terminal(cls) -> frozenset["ArchiveState"]:
        """COMPLETED and FAILED."""
        return frozenset({cls.COMPLETED, cls.FAILED})

    @classmethod
    def active(cls) -> frozenset["ArchiveState"]:
        """QUEUED and RUNNING."""
        return frozenset({cls.QUEUED, cls.RUNNING})


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
    path = status_path(experiment_id, data_dir)
    try:
        content = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return None
    except OSError:
        logger.exception("Failed to read archive status file %s", path)
        return None

    try:
        return ArchiveStatus.from_dict(json.loads(content))
    except json.JSONDecodeError:
        logger.error("Corrupt archive status file %s", path)
        return None


def write_status(
    status: ArchiveStatus,
    experiment_id: str,
    data_dir: Path,
    *,
    expected_attempt_id: str | None = None,
) -> bool:
    """Atomic write via temp file, fsync, rename; returns False if attempt-fenced."""
    path = status_path(experiment_id, data_dir)

    if expected_attempt_id is not None:
        existing = read_status(experiment_id, data_dir)
        if existing is not None and existing.attempt_id != expected_attempt_id:
            logger.warning(
                "Attempt fence: on-disk attempt %s != writer attempt %s, skipping status write",
                existing.attempt_id,
                expected_attempt_id,
            )
            return False

    path.parent.mkdir(parents=True, exist_ok=True)
    content = json.dumps(status.to_dict(), indent=2)

    fd, tmp_name = tempfile.mkstemp(
        dir=str(path.parent),
        prefix=STATUS_FILENAME + ".",
        suffix=STATUS_TMP_SUFFIX,
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(content)
            f.flush()
            os.fsync(f.fileno())
        Path(tmp_name).replace(path)
    except OSError:
        logger.exception("Failed to write archive status file %s", path)
        with contextlib.suppress(OSError):
            Path(tmp_name).unlink()
        raise

    return True


def create_queued_status(attempt_id: str, direction: str) -> ArchiveStatus:
    """Build the initial status the API writes at Job submission."""
    return ArchiveStatus(attempt_id=attempt_id, state=ArchiveState.QUEUED.value, direction=direction)
