"""Common utilities shared across Tuner engines."""

import asyncio
import hashlib
import logging
import os
import re
import shlex
import shutil
import time
from collections import deque
from pathlib import Path
from typing import Any, Literal

import ray
from fastapi import UploadFile

from api.config import INPUTS_DIR, JOBS_DIR
from api.schemas.common import ResourcesResponse

logger = logging.getLogger(__name__)

# Forbidden shell metacharacters for extra_args validation
_EXTRA_ARGS_FORBIDDEN_RE = re.compile(r"[;&|`$()<>]")

GMX_FORBIDDEN_FLAGS: frozenset[str] = frozenset({"-deffnm", "-s", "-ntomp", "-np", "-nb", "-pme"})
AMBER_FORBIDDEN_FLAGS: frozenset[str] = frozenset({"-i", "-p", "-c", "-o", "-inf", "-r", "-x", "-O"})


def save_upload(file: UploadFile, dest: Path) -> None:
    """Write an uploaded file to dest, creating parent directories as needed."""
    dest.parent.mkdir(parents=True, exist_ok=True)
    with dest.open("wb") as f:
        shutil.copyfileobj(file.file, f)


def cleanup_job_files(job_id: str) -> None:
    """Remove all temporary files associated with a job ID."""
    files_to_remove = [
        INPUTS_DIR / f"{job_id}_md.tpr",
        INPUTS_DIR / f"{job_id}_md.prmtop",
        INPUTS_DIR / f"{job_id}_md.inpcrd",
        INPUTS_DIR / f"{job_id}_md.mdin",
    ]
    for f in files_to_remove:
        if f.exists():
            try:
                f.unlink()
                logger.info("Deleted file: %s", f)
            except OSError:
                logger.exception("Failed to delete %s", f)

    trial_job_dir = JOBS_DIR / job_id
    if trial_job_dir.is_dir():
        try:
            shutil.rmtree(trial_job_dir)
            logger.info("Deleted trial directory: %s", trial_job_dir)
        except OSError:
            logger.exception("Failed to delete %s", trial_job_dir)


def sha256_of_file(path: Path | str, chunk_size: int = 8192) -> str:
    """Calculate SHA256 hash of a file using chunked reading."""
    hasher = hashlib.sha256()
    with Path(path).open("rb") as f:
        while chunk := f.read(chunk_size):
            hasher.update(chunk)
    return hasher.hexdigest()


_cluster_status_cache: dict[str, Any] = {"data": None, "time": 0.0}
CLUSTER_STATUS_TTL = 10.0
RAY_FETCH_TIMEOUT = 4.0


async def get_cluster_status() -> ResourcesResponse | None:
    """Get current Ray cluster resource usage with caching."""
    now = time.time()
    if now - _cluster_status_cache["time"] < CLUSTER_STATUS_TTL:
        return _cluster_status_cache["data"]

    def _fetch() -> ResourcesResponse | None:
        try:
            if not ray.is_initialized():
                return None
            total, avail = ray.cluster_resources(), ray.available_resources()
            return ResourcesResponse(
                total_cpus=int(total.get("CPU", 0)),
                total_gpus=int(total.get("GPU", 0)),
                available_cpus=int(avail.get("CPU", 0)),
                available_gpus=int(avail.get("GPU", 0)),
            )
        except Exception:
            logger.exception("Error fetching cluster status.")
            return None

    try:
        loop = asyncio.get_running_loop()
        data = await asyncio.wait_for(loop.run_in_executor(None, _fetch), timeout=RAY_FETCH_TIMEOUT)
    except TimeoutError:
        logger.warning("ray.cluster_resources() timed out after %.1fs", RAY_FETCH_TIMEOUT)
        _cluster_status_cache["time"] = time.time()
        return _cluster_status_cache["data"]

    _cluster_status_cache["data"] = data
    _cluster_status_cache["time"] = time.time()
    return data


def tail(file: Path | str, n: int = 10) -> str:
    """
    Read last n lines of a file efficiently.

    Returns empty string if file doesn't exist.
    """
    file_path = Path(file) if isinstance(file, str) else file
    try:
        with file_path.open("rb") as f:
            f.seek(0, os.SEEK_END)
            file_size = f.tell()
            if file_size == 0:
                return ""

            lines_found: deque[bytes] = deque()
            pos = file_size
            while pos > 0 and len(lines_found) < n:
                chunk_start = max(0, pos - 8192)
                f.seek(chunk_start)
                chunk = f.read(pos - chunk_start)
                chunk_lines = chunk.split(b"\n")
                if lines_found and chunk_lines:
                    lines_found[0] = chunk_lines.pop() + lines_found[0]
                lines_found.extendleft(reversed(chunk_lines))
                pos = chunk_start

            return b"\n".join(list(lines_found)[-n:]).decode("utf-8", "replace")
    except FileNotFoundError:
        logger.debug("File not found: %s", file_path)
        return ""


def read_trial_log(job_id: str, trial_id: str, stream: Literal["stdout", "stderr"]) -> str:
    """Read a trial's stdout or stderr log file. Returns empty string if not yet written."""
    base = JOBS_DIR.resolve()
    candidate = (JOBS_DIR / job_id / trial_id / f"{stream}.log").resolve()
    if not str(candidate).startswith(str(base) + os.sep):
        logger.warning("Path traversal attempt blocked: %s", candidate)
        return ""
    try:
        return candidate.read_text(encoding="utf-8", errors="replace")
    except FileNotFoundError:
        return ""


def _parse_nsteps_value(raw: str) -> int:
    try:
        value = int(raw)
    except ValueError:
        raise ValueError(f"-nsteps expects a positive integer, got '{raw}'") from None
    if value < 1:
        raise ValueError(f"-nsteps must be a positive integer, got {value}")
    return value


def extract_nsteps_override(extra_args: str) -> tuple[str, int | None]:
    """Return benchmark-safe args and the last production -nsteps override."""
    extra_args = (extra_args or "").strip()
    if not extra_args:
        return "", None

    try:
        tokens = shlex.split(extra_args, posix=True)
    except ValueError as e:
        raise ValueError(f"Invalid extra_args: {e}") from e

    remaining: list[str] = []
    override: int | None = None
    i = 0
    while i < len(tokens):
        token = tokens[i]
        if token == "-nsteps":
            i += 1
            if i >= len(tokens):
                raise ValueError("-nsteps requires a value")
            override = _parse_nsteps_value(tokens[i])
        elif token.startswith("-nsteps="):
            override = _parse_nsteps_value(token.split("=", 1)[1])
        else:
            remaining.append(token)
        i += 1
    return shlex.join(remaining), override


def sanitize_extra_args(extra_args: str, forbidden_flags: frozenset[str]) -> str:
    """
    Validate and normalize extra MD engine arguments.

    Args:
        extra_args: Raw extra arguments string from user input.
        forbidden_flags: Engine-specific flags that must not be overridden.

    Returns:
        Canonicalized extra arguments string.

    Raises:
        ValueError: If extra_args contains forbidden characters or flags.
    """
    extra_args = (extra_args or "").strip()
    if not extra_args:
        return ""

    if _EXTRA_ARGS_FORBIDDEN_RE.search(extra_args):
        raise ValueError("extra_args contains forbidden characters: ; & | ` $ ( ) < >")

    try:
        tokens = shlex.split(extra_args, posix=True)
    except ValueError as e:
        raise ValueError(f"Invalid extra_args: {e}") from e

    # Check both plain tokens and the flag part of "flag=value" syntax
    flag_names = {token.split("=")[0] for token in tokens}
    if flag_names & forbidden_flags:
        raise ValueError(f"extra_args must not override critical flags: {', '.join(sorted(forbidden_flags))}")

    return shlex.join(tokens)
