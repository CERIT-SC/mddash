"""Durable MDRepo upload status document (contract between Dashboard API and upload worker)."""

from __future__ import annotations

import logging
from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import TYPE_CHECKING, Any

from core.worker_jobs import read_status_doc, write_status_doc

if TYPE_CHECKING:
    from pathlib import Path

logger = logging.getLogger(__name__)

STATUS_FILENAME = ".mdrepo-upload.json"
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
        """COMPLETED and FAILED."""
        return frozenset({cls.COMPLETED, cls.FAILED})

    @classmethod
    def active(cls) -> frozenset["UploadState"]:
        """QUEUED and RUNNING."""
        return frozenset({cls.QUEUED, cls.RUNNING})


@dataclass
class FailedFile:
    """A file that failed during upload."""

    key: str
    error: str


@dataclass
class UploadStatus:
    """Only fields that are read back are stored; experiment_id is implicit from the file path."""

    attempt_id: str
    state: str
    reason: str | None = None
    total_files: int = 0
    completed_files: int = 0
    total_bytes: int = 0
    completed_bytes: int = 0
    failed_files: list[FailedFile] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """Serialise to a JSON-compatible dict."""
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> UploadStatus:
        """Tolerate missing fields (status files from older attempts may lack newer keys)."""
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
    if len(text) <= max_len:
        return text
    return text[: max_len - 3] + "..."


def _sanitize_error(text: str) -> str:
    """Redact OAuth credentials that may leak into error messages."""
    sanitized = text
    for redact in ("Bearer ", "access_token=", "refresh_token=", "client_secret="):
        if redact in sanitized:
            idx = sanitized.find(redact)
            sanitized = sanitized[: idx + len(redact)] + "[REDACTED]"
    return _truncate(sanitized, MAX_ERROR_SUMMARY)


def status_path(experiment_id: str, data_dir: Path) -> Path:
    return data_dir / experiment_id / STATUS_FILENAME


def read_status(experiment_id: str, data_dir: Path) -> UploadStatus | None:
    """Return None if the file does not exist or is corrupt."""
    data = read_status_doc(status_path(experiment_id, data_dir))
    return None if data is None else UploadStatus.from_dict(data)


def write_status(
    status: UploadStatus,
    experiment_id: str,
    data_dir: Path,
    *,
    expected_attempt_id: str | None = None,
) -> bool:
    """Atomic write; returns False if attempt-fenced (another attempt owns the doc)."""
    if expected_attempt_id is not None:
        existing = read_status(experiment_id, data_dir)
        if existing is not None and existing.attempt_id != expected_attempt_id:
            logger.warning(
                "Attempt fence: on-disk attempt %s != writer attempt %s, skipping status write",
                existing.attempt_id,
                expected_attempt_id,
            )
            return False
    write_status_doc(status_path(experiment_id, data_dir), status.to_dict())
    return True


def create_queued_status(attempt_id: str) -> UploadStatus:
    return UploadStatus(attempt_id=attempt_id, state=UploadState.QUEUED.value)
