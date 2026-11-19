"""Durable population receipt (contract between the Dashboard API and the worker)."""

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from core.config import DATA_DIR
from core.worker_jobs import read_status_doc, write_status_doc

logger = logging.getLogger(__name__)

RECEIPT_FILENAME = ".population-status.json"
STAGING_DIR_NAME = "data"
# Sync-excluded staging root: same PVC/filesystem as experiments (renames, not copies).
STAGING_CACHE_DIR = ".cache"


def operation_dir(operation_id: str) -> Path:
    """Staging root of one operation, beneath the S3-sync-excluded cache tree."""
    return DATA_DIR / STAGING_CACHE_DIR / "datahugger" / operation_id


def receipt_path(operation_id: str) -> Path:
    """Receipt beside the staged files (never inside the dataset layout)."""
    return operation_dir(operation_id) / RECEIPT_FILENAME


def staging_dir(operation_id: str) -> Path:
    """Directory the worker downloads the dataset into."""
    return operation_dir(operation_id) / STAGING_DIR_NAME


@dataclass
class PopulationReceipt:
    """Worker state written atomically; the API finalizes only a valid success receipt."""

    state: str
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """Serialise to a JSON-compatible dict."""
        return {"state": self.state, "error": self.error}

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "PopulationReceipt":
        """Tolerate missing fields (older attempts may lack newer keys)."""
        return cls(state=data.get("state", ""), error=data.get("error"))


def read_receipt(operation_id: str) -> PopulationReceipt | None:
    """Return None if the receipt is missing or corrupt."""
    data = read_status_doc(receipt_path(operation_id))
    return None if data is None else PopulationReceipt.from_dict(data)


def write_receipt(operation_id: str, state: str, error: str | None = None) -> None:
    """Atomic write via temp file, fsync, rename."""
    write_status_doc(receipt_path(operation_id), PopulationReceipt(state, error).to_dict())
