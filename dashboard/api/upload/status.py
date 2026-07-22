"""
Durable MDRepo upload status document.

The status file lives at ``/mddash/<experiment_id>/.mdrepo-upload.json`` and is
the contract between the Dashboard API (writes queued state, reads for status
queries) and the upload worker (writes after pod admission).

It never contains OAuth tokens, request headers, stack traces, or raw remote
response bodies.
"""

from __future__ import annotations

import contextlib
import json
import logging
import os
import tempfile
from dataclasses import asdict, dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

STATUS_FILENAME = ".mdrepo-upload.json"
STATUS_TMP_SUFFIX = ".tmp"
MAX_FAILED_KEYS = 50
MAX_ERROR_SUMMARY = 500

REASON_AUTH = "auth"
REASON_SOURCE = "source"
REASON_REMOTE = "remote"
REASON_TIMEOUT = "timeout"
REASON_CONTROLLER = "controller"
REASON_JOB_MISSING = "job_missing"
REASON_EMPTY = "empty"


class UploadState(str, Enum):
    """Upload states persisted in the status document."""

    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"

    @classmethod
    def terminal(cls) -> frozenset["UploadState"]:
        """
        COMPLETED and FAILED.

        Returns:
            Frozenset of terminal states.
        """
        return frozenset({cls.COMPLETED, cls.FAILED})

    @classmethod
    def active(cls) -> frozenset["UploadState"]:
        """
        QUEUED and RUNNING.

        Returns:
            Frozenset of active states.
        """
        return frozenset({cls.QUEUED, cls.RUNNING})


@dataclass
class FailedFile:
    """A file that failed during upload."""

    key: str
    error: str


@dataclass
class UploadStatus:
    """
    Only fields that are read back are stored.

    experiment_id is implicit from the file path, mdrepo_id/job_name live on
    the experiment row or are derivable, timestamps are not operationally needed.
    """

    attempt_id: str
    state: str
    reason: str | None = None
    total_files: int = 0
    completed_files: int = 0
    total_bytes: int = 0
    completed_bytes: int = 0
    failed_files: list[FailedFile] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """
        Serialise to a JSON-compatible dict.

        Returns:
            Dictionary representation.
        """
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> UploadStatus:
        """
        Tolerate missing fields (status files from older attempts may lack newer keys).

        Returns:
            Reconstructed status.
        """
        failed = data.get("failed_files") or []
        failed_files = [
            FailedFile(key=f.get("key", ""), error=_truncate(f.get("error", ""), MAX_ERROR_SUMMARY))
            for f in failed[:MAX_FAILED_KEYS]
            if isinstance(f, dict)
        ]
        return cls(
            attempt_id=data.get("attempt_id", ""),
            state=data.get("state", ""),
            reason=data.get("reason"),
            total_files=data.get("total_files", 0),
            completed_files=data.get("completed_files", 0),
            total_bytes=data.get("total_bytes", 0),
            completed_bytes=data.get("completed_bytes", 0),
            failed_files=failed_files,
        )


def _truncate(text: str, max_len: int) -> str:
    """
    Append ellipsis if shortened.

    Returns:
        Truncated string.
    """
    if len(text) <= max_len:
        return text
    return text[: max_len - 3] + "..."


def _sanitize_error(text: str) -> str:
    """
    Redact OAuth credentials that may leak into error messages before persisting.

    Returns:
        Redacted, truncated string.
    """
    sanitized = text
    for redact in ("Bearer ", "access_token=", "refresh_token=", "client_secret="):
        if redact in sanitized:
            idx = sanitized.find(redact)
            sanitized = sanitized[: idx + len(redact)] + "[REDACTED]"
    return _truncate(sanitized, MAX_ERROR_SUMMARY)


def status_path(experiment_id: str, data_dir: Path) -> Path:
    """
    Path to the .mdrepo-upload.json file.

    Returns:
        Absolute path to the status file.
    """
    return data_dir / experiment_id / STATUS_FILENAME


def read_status(experiment_id: str, data_dir: Path) -> UploadStatus | None:
    """
    Return None if the file does not exist or is corrupt.

    Returns:
        Parsed status, or None.
    """
    path = status_path(experiment_id, data_dir)
    try:
        content = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return None
    except OSError:
        logger.exception("Failed to read upload status file %s", path)
        return None

    try:
        return UploadStatus.from_dict(json.loads(content))
    except json.JSONDecodeError:
        logger.error("Corrupt upload status file %s", path)
        return None


def write_status(
    status: UploadStatus,
    experiment_id: str,
    data_dir: Path,
    *,
    expected_attempt_id: str | None = None,
) -> bool:
    """
    Atomically write via temp file, fsync, rename.

    If ``expected_attempt_id`` is provided and the on-disk attempt ID differs,
    the write is skipped (attempt fencing) and False is returned. This prevents
    a stale worker from overwriting a newer attempt's status.

    Returns:
        True if written, False if fenced.

    Raises:
        OSError: If the atomic write fails after fencing check passes.
    """
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
        logger.exception("Failed to write upload status file %s", path)
        with contextlib.suppress(OSError):
            Path(tmp_name).unlink()
        raise

    return True


def create_queued_status(attempt_id: str) -> UploadStatus:
    """
    Create the initial queued status for a new upload attempt.

    Returns:
        A new UploadStatus in the queued state.
    """
    return UploadStatus(attempt_id=attempt_id, state=UploadState.QUEUED.value)
