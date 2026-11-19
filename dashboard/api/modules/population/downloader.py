"""Pinned Datahugger-NG binding boundary (datahugger-ng==0.6.9)."""

import re
from pathlib import Path, PurePosixPath
from urllib.parse import urlsplit

# Fixed download concurrency; the binding's zero/unlimited default must not be used.
DOWNLOAD_CONCURRENCY = 4

ERROR_UNRECOGNIZED = (
    "Datahugger-NG does not recognize this repository URL. "
    "Verify the URL and check that the repository is publicly accessible."
)
ERROR_CONNECTION = (
    "The public repository could not be contacted. Retry later or contact support if the failure persists."
)
ERROR_STORAGE = (
    "The downloaded repository could not be saved. Free up storage or contact support if the problem persists."
)
ERROR_VALIDATION = "The downloaded repository files failed size or checksum validation."
ERROR_DOWNLOAD = "The repository download failed. Contact support if the failure persists."

# The pinned Rust binding exposes these failures as RuntimeError strings, not structured Python errors.
# Match the entire message and only copy a validated source filename, never an arbitrary exception fragment.
_HTTP_REQUEST = re.compile(r"fail to send http GET to (?P<url>https?://[^\s,]+),? to get file '(?P<filename>[^']+)'")
_MAX_SAFE_FILENAME_LENGTH = 512
_MAX_HOSTNAME_LENGTH = 253


class PopulationDownloadError(Exception):
    """A safe download failure curated from the pinned native binding's error boundary."""


def _safe_filename(text: str) -> str | None:
    """Keep a verified relative repository path from a recognized message, never its URL or local path."""
    http_match = _HTTP_REQUEST.fullmatch(text)
    if http_match is None:
        return None
    path = http_match["filename"]
    filename = PurePosixPath(path)
    if (
        not path
        or len(path) > _MAX_SAFE_FILENAME_LENGTH
        or filename.is_absolute()
        or any(not part or part in {".", ".."} for part in filename.parts)
        or any(not char.isprintable() for char in path)
    ):
        return None
    return filename.as_posix().removeprefix("__ROOT__/")


def _safe_host(text: str) -> str:
    """Return only the public hostname from a native URL; never its path/query/user-info."""
    match = re.search(r"\bGET (?P<url>https?://[^\s,]+)", text)
    if match is None:
        return ""
    hostname = urlsplit(match["url"]).hostname
    if hostname is None or len(hostname) > _MAX_HOSTNAME_LENGTH or not re.fullmatch(r"[A-Za-z0-9.-]+", hostname):
        return ""
    return hostname


def sanitize_download_exception(exc: Exception) -> PopulationDownloadError:
    """Translate pinned native error shapes to curated text; unmatched native details stay private."""
    text = str(exc)
    filename = _safe_filename(text.removeprefix("crawler fail: "))

    if text.startswith(("unknown domain:", "cannot get fragment of url", "expected url to end with 'overview'")):
        return PopulationDownloadError(ERROR_UNRECOGNIZED)
    if "unable to parse Mdepsoit dataset id" in text or "not a valid url" in text:
        return PopulationDownloadError(ERROR_UNRECOGNIZED)
    if "resource not found when GET " in text:
        host = _safe_host(text)
        return PopulationDownloadError(
            f"The repository or dataset was not found{f' at {host}' if host else ''}. "
            "Verify its URL and that it is public."
        )
    if "with state code:" in text:
        status_match = re.search(r"with state code: (?P<status>[1-5][0-9]{2})\b", text)
        if status_match and status_match["status"] in {"401", "403"}:
            return PopulationDownloadError("The repository denied public access. Choose a publicly accessible dataset.")
        status = f" (HTTP {status_match['status']})" if status_match else ""
        return PopulationDownloadError(f"The public repository returned an HTTP error{status}. Retry later.")
    if "fail at client sent GET " in text or "network / protocol error" in text:
        return PopulationDownloadError(ERROR_CONNECTION)
    if filename is not None:
        return PopulationDownloadError(f"The repository could not provide file '{filename}'. {ERROR_CONNECTION}")
    if "unable to convert to json" in text or "fail to extract" in text or "expected array" in text:
        return PopulationDownloadError(
            "The repository returned metadata that Datahugger-NG could not process. "
            "Verify the repository URL or contact support."
        )
    if any(
        marker in text
        for marker in (
            "cannot create dir",
            "connot create folder dir",
            "fail at writing to fs",
            "fail on create file at",
        )
    ):
        return PopulationDownloadError(ERROR_STORAGE)
    if "size wrong," in text or "checksum wrong," in text:
        return PopulationDownloadError(ERROR_VALIDATION)
    return PopulationDownloadError(ERROR_DOWNLOAD)


def download_dataset(repo_url: str, dst_dir: Path) -> int:
    """
    Resolve the public repository and download its full contents into `dst_dir` with validation.

    Blocking: the binding runs its own runtime and the worker performs it as the whole Job.
    Native failures are translated into stable user-facing messages; their raw details are
    logged only by the worker and never included in the domain exception.
    """
    # Imported lazily so tests can fake the pinned binding without the native package.
    from datahugger import resolve  # ruff:ignore[import-outside-top-level]

    try:
        dataset = resolve(repo_url)
        return dataset.download_with_validation(dst_dir=dst_dir, limit=DOWNLOAD_CONCURRENCY)
    except PopulationDownloadError:
        raise
    except Exception as exc:
        raise sanitize_download_exception(exc) from exc
