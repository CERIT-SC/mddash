#!/usr/bin/env python3
"""Standalone MDRepo upload worker for the durable upload Kubernetes Job."""

from __future__ import annotations

import argparse
import contextlib
import hashlib
import json
import logging
import os
import subprocess
import sys
import tempfile
import time
from dataclasses import asdict, dataclass, field
from http import HTTPStatus
from pathlib import Path
from typing import Any

import requests

logger = logging.getLogger("mdrepo-uploader")

STATUS_FILENAME = ".mdrepo-upload.json"
STATUS_TMP_SUFFIX = ".tmp"
MAX_FAILED_KEYS = 50
MAX_ERROR_SUMMARY = 500
FILTERS_FILE = "/rclone-filters.txt"
DATA_DIR = Path("/mddash")

TOKEN_SAFETY_WINDOW = 60  # seconds before expiry to proactively refresh
TOKEN_REFRESH_RETRIES = 3
TOKEN_REFRESH_INITIAL_DELAY = 1
UPLOAD_TIMEOUT = 300
INIT_TIMEOUT = 30
COMMIT_TIMEOUT = 30
MAX_RETRIES = 5
INITIAL_BACKOFF = 1.0
MAX_BACKOFF = 30.0

REASON_AUTH = "auth"
REASON_SOURCE = "source"
REASON_REMOTE = "remote"
REASON_TIMEOUT = "timeout"
REASON_CONTROLLER = "controller"
REASON_EMPTY = "empty"

STATE_QUEUED = "queued"
STATE_RUNNING = "running"
STATE_COMPLETED = "completed"
STATE_FAILED = "failed"

RETRYABLE_STATUS = {429, 500, 502, 503, 504}
HTTP_BAD_REQUEST = HTTPStatus.BAD_REQUEST
HTTP_UNAUTHORIZED = HTTPStatus.UNAUTHORIZED
HTTP_NOT_FOUND = HTTPStatus.NOT_FOUND


@dataclass
class FailedFile:
    """A file that failed during upload."""

    key: str
    error: str


@dataclass
class UploadStatus:
    """Durable status document mirroring the API-side UploadStatus."""

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
    Redact OAuth credentials that may leak into error messages.

    Returns:
        Redacted, truncated string.
    """
    sanitized = text
    for redact in ("Bearer ", "access_token=", "refresh_token=", "client_secret="):
        if redact in sanitized:
            idx = sanitized.find(redact)
            sanitized = sanitized[: idx + len(redact)] + "[REDACTED]"
    return _truncate(sanitized, MAX_ERROR_SUMMARY)


def status_path(experiment_id: str) -> Path:
    """
    Path to the status file.

    Returns:
        Absolute path to .mdrepo-upload.json.
    """
    return DATA_DIR / experiment_id / STATUS_FILENAME


def read_status(experiment_id: str) -> UploadStatus | None:
    """
    Read the upload status from the PVC.

    Returns:
        Parsed status, or None if the file is missing or corrupt.
    """
    path = status_path(experiment_id)
    try:
        content = path.read_text(encoding="utf-8")
    except (FileNotFoundError, OSError):
        return None
    try:
        data = json.loads(content)
    except json.JSONDecodeError:
        return None
    failed = data.get("failed_files") or []
    failed_files = [
        FailedFile(key=f.get("key", ""), error=_truncate(f.get("error", ""), MAX_ERROR_SUMMARY))
        for f in failed[:MAX_FAILED_KEYS]
        if isinstance(f, dict)
    ]
    return UploadStatus(
        attempt_id=data.get("attempt_id", ""),
        state=data.get("state", ""),
        reason=data.get("reason"),
        total_files=data.get("total_files", 0),
        completed_files=data.get("completed_files", 0),
        total_bytes=data.get("total_bytes", 0),
        completed_bytes=data.get("completed_bytes", 0),
        failed_files=failed_files,
    )


def write_status(status: UploadStatus, experiment_id: str, *, expected_attempt_id: str | None = None) -> bool:
    """
    Atomically write the status document (temp file, fsync, rename).

    If ``expected_attempt_id`` is provided and the on-disk attempt ID differs,
    the write is skipped (attempt fencing) and False is returned.

    Returns:
        True if written, False if fenced.

    Raises:
        OSError: If the atomic write fails after fencing check passes.
    """
    path = status_path(experiment_id)

    if expected_attempt_id is not None:
        existing = read_status(experiment_id)
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


class WorkerTokenManager:
    """Manage OAuth2 token refresh for the upload worker lifetime."""

    def __init__(self) -> None:
        """Load credentials from environment variables set via the K8s Secret."""
        self.access_token = os.environ.get("MDREPO_ACCESS_TOKEN", "")
        self.refresh_token = os.environ.get("MDREPO_REFRESH_TOKEN", "")
        self.client_id = os.environ.get("MDREPO_CLIENT_ID", "")
        self.client_secret = os.environ.get("MDREPO_CLIENT_SECRET", "")
        self.token_url = os.environ.get("MDREPO_TOKEN_URL", "")
        try:
            self.expires_at = float(os.environ.get("MDREPO_TOKEN_EXPIRES_AT", "0"))
        except (ValueError, TypeError):
            self.expires_at = 0.0

    def get_valid_token(self) -> str | None:
        """
        Return a valid access token, refreshing if within the safety window.

        Returns:
            Access token string, or None if no token is available.
        """
        if not self.access_token:
            return None
        if time.time() >= self.expires_at - TOKEN_SAFETY_WINDOW:
            self._refresh()
        return self.access_token if self.access_token else None

    def _refresh(self) -> None:
        """
        Refresh the access token using the refresh-token grant.

        Raises:
            RuntimeError: If the refresh token is missing, invalid, or all retries fail.
        """
        if not self.refresh_token:
            logger.error("No refresh token available for worker")
            raise RuntimeError("No refresh token available")

        token_data = {
            "grant_type": "refresh_token",
            "refresh_token": self.refresh_token,
            "client_id": self.client_id,
            "client_secret": self.client_secret,
        }

        for attempt in range(TOKEN_REFRESH_RETRIES):
            try:
                response = requests.post(self.token_url, data=token_data, timeout=30)
                if response.ok:
                    token_response = response.json()
                    self.access_token = token_response.get("access_token", "")
                    if "refresh_token" in token_response:
                        new_rt = token_response.get("refresh_token")
                        if new_rt:
                            self.refresh_token = new_rt
                    expires_in = token_response.get("expires_in", 3600)
                    self.expires_at = time.time() + expires_in
                    logger.info("Worker token refreshed successfully")
                    return
                logger.error("Token refresh failed: %s - %s", response.status_code, response.text)
                if response.status_code == HTTP_BAD_REQUEST:
                    raise RuntimeError("Refresh token invalid or expired")
                if attempt < TOKEN_REFRESH_RETRIES - 1:
                    delay = TOKEN_REFRESH_INITIAL_DELAY * (2**attempt)
                    time.sleep(delay)
            except requests.RequestException as e:
                logger.error("Token refresh request failed: %s", e)
                if attempt < TOKEN_REFRESH_RETRIES - 1:
                    delay = TOKEN_REFRESH_INITIAL_DELAY * (2**attempt)
                    time.sleep(delay)

        raise RuntimeError("Token refresh failed after all retries")

    def handle_401(self) -> bool:
        """
        Attempt one refresh on 401 Unauthorized.

        Returns:
            True if the token was refreshed, False otherwise.
        """
        if not self.refresh_token:
            return False
        try:
            self._refresh()
            return True
        except RuntimeError:
            return False


class InvenioClient:
    """InvenioRDM draft file operations with retry and token refresh."""

    def __init__(self, token_manager: WorkerTokenManager) -> None:
        """Initialize with a token manager and endpoint config from the environment."""
        self.tm = token_manager
        self.api_url = os.environ.get("MDREPO_API_URL", "")
        self.record_name = os.environ.get("MDREPO_RECORD_NAME", "datasets")

    def _headers(self) -> dict[str, str]:
        """
        Return authorization headers with a valid token.

        Returns:
            Dict with Authorization header.

        Raises:
            RuntimeError: If no valid token is available.
        """
        token = self.tm.get_valid_token()
        if not token:
            raise RuntimeError("No valid access token")
        return {"Authorization": f"Bearer {token}"}

    def _url(self, draft_id: str, *parts: str) -> str:
        """
        Build a draft files API URL.

        Returns:
            Fully-qualified URL string.
        """
        base = f"{self.api_url}/{self.record_name}/{draft_id}/draft/files"
        if parts:
            base += "/" + "/".join(parts)
        return base

    def list_files(self, draft_id: str) -> dict[str, dict[str, Any]]:
        """
        Return a dict of key -> file metadata from the draft.

        Returns:
            Dict mapping file key to {size, checksum, completed}.
        """
        result: dict[str, dict[str, Any]] = {}
        try:
            resp = self._request("GET", self._url(draft_id), timeout=INIT_TIMEOUT)
            if resp.ok:
                for entry in resp.json().get("entries", []):
                    key = entry.get("key", "")
                    if key:
                        result[key] = {
                            "size": entry.get("size", 0),
                            "checksum": entry.get("checksum", ""),
                            "completed": entry.get("status") == STATE_COMPLETED,
                        }
        except Exception:
            logger.exception("Failed to list draft files")
        return result

    def delete_file(self, draft_id: str, key: str) -> bool:
        """
        Delete a file from the draft (idempotent — 404 is success).

        Returns:
            True if deleted or already gone, False on error.
        """
        try:
            resp = self._request("DELETE", self._url(draft_id, key), timeout=INIT_TIMEOUT)
            return resp.ok or resp.status_code == HTTP_NOT_FOUND
        except Exception:
            logger.exception("Failed to delete draft file %s", key)
            return False

    def initialize_file(self, draft_id: str, key: str) -> bool:
        """
        Initialize a file upload slot in the draft.

        Returns:
            True if initialized, False on error.
        """
        try:
            resp = self._request("POST", self._url(draft_id), json=[{"key": key}], timeout=INIT_TIMEOUT)
            return resp.ok
        except Exception:
            return False

    def stream_content(self, draft_id: str, key: str, file_path: Path) -> bool:
        """
        Stream file content to the draft.

        Returns:
            True if uploaded, False on error.
        """
        try:
            with file_path.open("rb") as f:
                resp = self._request("PUT", self._url(draft_id, key, "content"), data=f, timeout=UPLOAD_TIMEOUT)
            return resp.ok
        except Exception:
            return False

    def commit_file(self, draft_id: str, key: str) -> dict[str, Any] | None:
        """
        Commit an uploaded file in the draft.

        Returns:
            Commit response dict, or None on failure.
        """
        try:
            resp = self._request("POST", self._url(draft_id, key, "commit"), timeout=COMMIT_TIMEOUT)
            if resp.ok:
                return resp.json()
        except Exception:
            pass
        return None

    def _request(self, method: str, url: str, **kwargs: Any) -> requests.Response:  # ruff:ignore[any-type]  # passthrough to requests.request
        """
        Execute an HTTP request with retry and 401-refresh logic.

        Returns:
            The HTTP response.

        Raises:
            requests.ConnectionError: If the connection fails after all retries.
            requests.Timeout: If the request times out after all retries.
        """
        for attempt in range(MAX_RETRIES):
            headers = self._headers()
            kwargs.setdefault("headers", {}).update(headers)
            try:
                resp = requests.request(method, url, **kwargs)
                if resp.status_code == HTTP_UNAUTHORIZED and self.tm.handle_401():
                    continue
                if resp.status_code in RETRYABLE_STATUS and attempt < MAX_RETRIES - 1:
                    delay = min(INITIAL_BACKOFF * (2**attempt), MAX_BACKOFF)
                    logger.warning("Retryable %s on %s %s, backing off %.1fs", resp.status_code, method, url, delay)
                    time.sleep(delay)
                    continue
                return resp
            except (requests.ConnectionError, requests.Timeout) as e:
                if attempt < MAX_RETRIES - 1:
                    delay = min(INITIAL_BACKOFF * (2**attempt), MAX_BACKOFF)
                    logger.warning("Connection error on %s %s: %s, backing off %.1fs", method, url, e, delay)
                    time.sleep(delay)
                    continue
                raise
        return resp  # type: ignore[possibly-undefined]


def list_eligible_files(experiment_id: str) -> list[tuple[str, Path]]:
    """
    List eligible files under the experiment directory using the rclone filter.

    Returns:
        List of (relative_key, absolute_path) tuples.

    Raises:
        subprocess.CalledProcessError: If rclone fails.
        subprocess.TimeoutExpired: If rclone times out.
    """
    try:
        result = subprocess.run(
            [
                "rclone",
                "lsf",
                str(DATA_DIR) + "/",
                "--filter-from",
                FILTERS_FILE,
                "--recursive",
                "--files-only",
            ],
            capture_output=True,
            text=True,
            timeout=120,
            check=True,
        )
    except subprocess.CalledProcessError as e:
        logger.error("rclone lsf failed: %s\nstderr: %s", e, e.stderr)
        raise
    except subprocess.TimeoutExpired:
        logger.error("rclone lsf timed out")
        raise

    files: list[tuple[str, Path]] = []
    for raw_line in result.stdout.strip().splitlines():
        stripped = raw_line.strip()
        if not stripped:
            continue
        parts = stripped.split("/")
        if not parts or parts[0] != experiment_id:
            continue
        relative_key = "/".join(parts[1:])
        if not relative_key:
            continue
        abs_path = DATA_DIR / stripped
        if abs_path.is_file():
            files.append((relative_key, abs_path))

    return files


def compute_file_md5(file_path: Path) -> str:
    """
    Compute the MD5 hex digest of a file.

    Returns:
        MD5 hex digest string.
    """
    md5 = hashlib.md5()
    with file_path.open("rb") as f:
        for chunk in iter(lambda: f.read(128 * 1024), b""):
            md5.update(chunk)
    return md5.hexdigest()


def get_file_identity(file_path: Path) -> dict[str, Any]:
    """
    Return size, mtime, and inode for a file path.

    Returns:
        Dict with size, mtime, and inode keys.
    """
    stat = file_path.stat()
    return {
        "size": stat.st_size,
        "mtime": stat.st_mtime,
        "inode": stat.st_ino,
    }


def verify_file_identity(file_path: Path, original: dict[str, Any]) -> bool:
    """
    Verify that a file's size, mtime, and inode haven't changed.

    Returns:
        True if unchanged, False otherwise.
    """
    current = get_file_identity(file_path)
    return (
        current["size"] == original["size"]
        and current["mtime"] == original["mtime"]
        and current["inode"] == original["inode"]
    )


def _is_already_committed(
    path: Path,
    identity: dict[str, Any],
    existing: dict[str, Any],
) -> bool:
    """
    Check if a file is already committed with matching size and checksum.

    Returns:
        True if the file is already committed and unchanged, False otherwise.
    """
    if not existing.get("completed"):
        return False
    local_md5 = compute_file_md5(path)
    remote_checksum = existing.get("checksum", "")
    remote_md5 = ""
    if ":" in remote_checksum:
        remote_md5 = remote_checksum.split(":", 1)[1]
    return existing.get("size") == identity["size"] and bool(remote_md5) and local_md5 == remote_md5


def run_worker(experiment_id: str, mdrepo_id: str, attempt_id: str) -> int:
    """
    Run the upload worker entry point.

    Returns:
        Exit code (0 = success, 1 = failure).
    """
    logging.basicConfig(
        level=logging.INFO,
        format="[%(asctime)s] %(levelname)s\t%(name)s: %(message)s",
    )

    logger.info("Starting upload worker: experiment=%s draft=%s attempt=%s", experiment_id, mdrepo_id, attempt_id)

    tm = WorkerTokenManager()
    if not tm.access_token:
        logger.error("No access token in environment")
        _write_failed(experiment_id, attempt_id, REASON_AUTH, "No access token")
        return 1

    status = UploadStatus(attempt_id=attempt_id, state=STATE_RUNNING)
    write_status(status, experiment_id, expected_attempt_id=attempt_id)

    try:
        return _do_upload(experiment_id, mdrepo_id, attempt_id, tm, status)
    except Exception as e:
        logger.exception("Upload worker failed with unexpected error")
        status.state = "failed"
        status.reason = REASON_CONTROLLER
        status.failed_files = [FailedFile(key="", error=_sanitize_error(str(e)))]
        write_status(status, experiment_id, expected_attempt_id=attempt_id)
        return 1


def _record_failure(
    status: UploadStatus,
    failed_files: list[FailedFile],
    key: str,
    error: str,
    experiment_id: str,
    attempt_id: str,
) -> None:
    """Append a failed file, update status, and persist."""
    failed_files.append(FailedFile(key=key, error=_sanitize_error(error)))
    status.failed_files = failed_files[:MAX_FAILED_KEYS]
    write_status(status, experiment_id, expected_attempt_id=attempt_id)


def _do_upload(
    experiment_id: str,
    mdrepo_id: str,
    attempt_id: str,
    tm: WorkerTokenManager,
    status: UploadStatus,
) -> int:
    """
    Execute the upload flow.

    Returns:
        Exit code (0 = success, 1 = failure).
    """
    files = list_eligible_files(experiment_id)
    if not files:
        logger.error("No eligible files found for experiment %s", experiment_id)
        status.state = "failed"
        status.reason = REASON_EMPTY
        write_status(status, experiment_id, expected_attempt_id=attempt_id)
        return 1

    file_identities: dict[str, dict[str, Any]] = {}
    total_bytes = 0
    for key, path in files:
        identity = get_file_identity(path)
        file_identities[key] = identity
        total_bytes += identity["size"]

    status.total_files = len(files)
    status.total_bytes = total_bytes
    write_status(status, experiment_id, expected_attempt_id=attempt_id)

    logger.info("Found %d eligible files (%d bytes) for experiment %s", len(files), total_bytes, experiment_id)

    client = InvenioClient(tm)
    draft_files = client.list_files(mdrepo_id)
    logger.info("Draft %s has %d existing files", mdrepo_id, len(draft_files))

    failed_files: list[FailedFile] = []
    completed_bytes = 0
    completed_count = 0

    for key, path in files:
        identity = file_identities[key]
        existing = draft_files.get(key)

        # Skip if already committed with matching checksum.
        if existing and _is_already_committed(path, identity, existing):
            logger.info("Skipping already committed file: %s", key)
            completed_bytes += identity["size"]
            completed_count += 1
            status.completed_files = completed_count
            status.completed_bytes = completed_bytes
            write_status(status, experiment_id, expected_attempt_id=attempt_id)
            continue

        # Remove or replace incomplete/mismatched entries.
        if existing:
            logger.info("Removing incomplete/mismatched draft file: %s", key)
            client.delete_file(mdrepo_id, key)

        if not _upload_single_file(
            client, mdrepo_id, key, path, identity, status, failed_files, experiment_id, attempt_id
        ):
            continue

        completed_bytes += identity["size"]
        completed_count += 1
        status.completed_files = completed_count
        status.completed_bytes = completed_bytes
        write_status(status, experiment_id, expected_attempt_id=attempt_id)
        logger.info("Committed file %d/%d: %s", completed_count, len(files), key)

    if failed_files:
        status.state = "failed"
        status.reason = REASON_REMOTE if any(f.key for f in failed_files) else REASON_SOURCE
        status.failed_files = failed_files[:MAX_FAILED_KEYS]
        write_status(status, experiment_id, expected_attempt_id=attempt_id)
        logger.error("Upload completed with %d failed files", len(failed_files))
        return 1

    status.state = "completed"
    status.completed_files = completed_count
    status.completed_bytes = completed_bytes
    write_status(status, experiment_id, expected_attempt_id=attempt_id)
    logger.info("Upload completed successfully: %d files, %d bytes", completed_count, completed_bytes)
    return 0


def _upload_single_file(
    client: InvenioClient,
    mdrepo_id: str,
    key: str,
    path: Path,
    identity: dict[str, Any],
    status: UploadStatus,
    failed_files: list[FailedFile],
    experiment_id: str,
    attempt_id: str,
) -> bool:
    """
    Initialize, stream, and commit a single file.

    Returns:
        True on success, False on failure.
    """
    if not client.initialize_file(mdrepo_id, key):
        _record_failure(status, failed_files, key, f"Failed to initialize file: {key}", experiment_id, attempt_id)
        return False

    # Verify source identity before and after reading to detect mutations.
    if not verify_file_identity(path, identity):
        _record_failure(
            status, failed_files, key, f"Source file changed before upload: {key}", experiment_id, attempt_id
        )
        return False

    if not verify_file_identity(path, identity):
        _record_failure(status, failed_files, key, f"Source file changed during read: {key}", experiment_id, attempt_id)
        return False

    if not client.stream_content(mdrepo_id, key, path):
        _record_failure(status, failed_files, key, f"Failed to stream file content: {key}", experiment_id, attempt_id)
        return False

    if client.commit_file(mdrepo_id, key) is None:
        _record_failure(status, failed_files, key, f"Failed to commit file: {key}", experiment_id, attempt_id)
        return False

    if not verify_file_identity(path, identity):
        _record_failure(
            status, failed_files, key, f"Source file changed after upload: {key}", experiment_id, attempt_id
        )
        return False

    return True


def _write_failed(experiment_id: str, attempt_id: str, reason: str, error: str) -> None:
    """Write a terminal failed status document."""
    status = UploadStatus(
        attempt_id=attempt_id,
        state=STATE_FAILED,
        reason=reason,
        failed_files=[FailedFile(key="", error=_sanitize_error(error))],
    )
    write_status(status, experiment_id, expected_attempt_id=attempt_id)


def main() -> None:
    """Parse CLI arguments and run the worker."""
    parser = argparse.ArgumentParser(description="MDRepo upload worker")
    parser.add_argument("--experiment-id", required=True, help="Local experiment ID")
    parser.add_argument("--mdrepo-id", required=True, help="MDRepo draft ID")
    parser.add_argument("--attempt-id", required=True, help="Upload attempt ID")
    args = parser.parse_args()

    exit_code = run_worker(args.experiment_id, args.mdrepo_id, args.attempt_id)
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
