import fnmatch
import logging
import os
import random
import re
import shutil
import subprocess
import tempfile
import threading
import time
from collections import deque
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse

from werkzeug.exceptions import InternalServerError, NotFound

logger = logging.getLogger(__name__)

LETTERS = "abcdefghijklmnopqrstuvwxyz"

EXCLUDED_DIRS: list[str] = [
    ".ipynb_checkpoints",
    "__pycache__",
    ".cache",
    ".local",
    ".config",
    ".jupyter",
    ".git",
    ".binder-env",
    "*.edr",
    "*.xtc",
    "*.tpr",
    "*.cpt",
    "*.gro",
    "*.log",
    "analysis/mwf",
]

EXCLUDED_FILES: list[str] = [
    "#*#",
    "*.swp",
    "*.tmp",
    ".gitkeep",
    ".nfs*",
    ".binder-env-installed",
    "inputs.yaml",
    ".storage_size",
    ".storage_size.tmp*",
]


@dataclass
class FileInfo:
    """Data class representing a file with its name, size, and relative path."""

    name: str
    size: int
    path: str


def generate_id(length: int = 5) -> str:
    """
    Generate a random lowercase alphabetic ID.

    Args:
        length: Length of the ID to generate.

    Returns:
        Random string of lowercase letters.
    """
    return "".join(random.choice(LETTERS) for _ in range(length))


def get_unique_id(id_dir: Path) -> str:
    """
    Generate a unique ID that doesn't exist in the given directory.

    Args:
        id_dir: Directory to check for existing IDs.

    Returns:
        Unique 5-character lowercase alphabetic ID.

    Raises:
        ValueError: If too many experiments exist (all IDs exhausted).
    """
    id_length = 5
    id = generate_id(id_length)

    iters = 0
    max_iters = 10_000_000  # 26^5 = 11,881,376

    while (id_dir / id).exists():
        id = generate_id(id_length)

        iters += 1
        if iters > max_iters:
            raise ValueError("You have too many experiments!")

    return id


def get_files_with_extensions(
    dir: Path, ext: str | list[str] | None = None, base_dir: Path | None = None
) -> list[FileInfo]:
    """
    Get all files in a directory, optionally filtered by extension.

    Args:
        dir: Directory to search for files.
        ext: File extension(s) to filter by (e.g., 'txt', ['tpr', 'gro']).
             If None, returns all files.
        base_dir: Base directory for calculating relative paths (used internally for recursion).

    Returns:
        list[FileInfo]: List of FileInfo objects with file name, size, and relative path.

    Raises:
        ValueError: If dir is not a directory.
    """
    if not dir.is_dir():
        raise ValueError(f"{dir} is not a directory")

    if base_dir is None:
        base_dir = dir

    extensions = None
    if ext is not None:
        extensions = [e.lower() for e in ext] if isinstance(ext, list) else [ext.lower()]

    files = []

    for item in dir.iterdir():
        if is_excluded_path(item, base_dir):
            continue

        if item.is_file():
            relative_path = str(item.relative_to(base_dir))
            if extensions is None:
                files.append(FileInfo(name=item.name, size=item.stat().st_size, path=relative_path))
            else:
                file_ext = item.suffix.lstrip(".").lower()
                if file_ext in extensions:
                    files.append(FileInfo(name=item.name, size=item.stat().st_size, path=relative_path))
        elif item.is_dir():
            files.extend(get_files_with_extensions(item, ext, base_dir))

    return files


_NSTEPS_RE = re.compile(r"-nsteps(?:=|\s+)['\"]?(\d+)")


def nsteps_override(extra_args: str) -> int | None:
    """Extract the effective GROMACS ``-nsteps`` override from extra_args (last occurrence wins), or None."""
    value = int(matches[-1]) if (matches := _NSTEPS_RE.findall(extra_args or "")) else 0
    return value if value > 0 else None


def is_excluded_path(path: Path, base_dir: Path) -> bool:
    """
    Determine whether a path should be excluded from uploads.

    Args:
        path: Path to evaluate.
        base_dir: Base directory for relative path matching.

    Returns:
        True if the path should be excluded.
    """
    try:
        relative_path = path.relative_to(base_dir)
    except ValueError:
        relative_path = path

    dir_parts = relative_path.parts if path.is_dir() else relative_path.parts[:-1]

    if any(fnmatch.fnmatch(part, pattern) for part in dir_parts for pattern in EXCLUDED_DIRS):
        return True

    return any(fnmatch.fnmatch(path.name, pattern) for pattern in EXCLUDED_FILES)


def tail(file: Path | str, n: int = 10) -> str:
    """
    Read last n lines of a file efficiently by reading chunks from the end.

    Args:
        file: Path to the file.
        n: Number of lines to read from the end of the file.

    Returns:
        str: Last n lines of the file as a string.
    """
    file_path = Path(file) if isinstance(file, str) else file
    with file_path.open("rb") as f:
        f.seek(0, os.SEEK_END)
        file_size = f.tell()

        if file_size == 0:
            return ""

        lines_found: deque[bytes] = deque()
        pos = file_size

        while pos > 0 and len(lines_found) < n:
            chunk_start = max(0, pos - 8192)
            chunk_size = pos - chunk_start

            f.seek(chunk_start)
            chunk = f.read(chunk_size)

            chunk_lines = chunk.split(b"\n")

            # handle partial line at the end of the chunk
            if lines_found and chunk_lines:
                lines_found[0] = chunk_lines.pop() + lines_found[0]

            # Prepend newly read lines to the deque
            lines_found.extendleft(reversed(chunk_lines))

            pos = chunk_start

        result_lines = list(lines_found)[-n:]
        return b"\n".join(result_lines).decode("utf-8", "replace")


DU_SIZE_FILENAME = ".storage_size"
DU_INTERVAL = 30 * 60  # 30 minutes


def get_du_size(data_dir: Path) -> int | None:
    """
    Read the last measured storage size of data_dir.

    Args:
        data_dir: Directory whose size to read.

    Returns:
        Total size in bytes, or None if not yet measured.
    """
    try:
        return int((data_dir / DU_SIZE_FILENAME).read_text().strip())
    except Exception:
        return None


def _du_loop(data_dir: Path, initial_delay: float = 0.0) -> None:
    """Background thread body: measure data_dir and per-experiment sizes every DU_INTERVAL seconds."""
    if initial_delay > 0:
        time.sleep(initial_delay)
    while True:
        try:
            # --max-depth=1 reports each entry inside data_dir plus the total in one pass
            result = subprocess.run(
                ["du", "-b", "--max-depth=1", str(data_dir)],
                capture_output=True,
                text=True,
                check=True,
            )
            for line in result.stdout.splitlines():
                size_s, _, path_s = line.rstrip("/").partition("\t")
                path = Path(path_s)
                # A marker can only live inside a directory: skip top-level files,
                # and skip hidden dirs (.rclone-bisync, .ipynb_checkpoints) entirely.
                if path != data_dir and (path.name.startswith(".") or not path.is_dir()):
                    continue
                try:
                    # atomic: two monitor threads (Flask reloader parent + child) race on these files
                    tmp = path / f"{DU_SIZE_FILENAME}.tmp{os.getpid()}"
                    tmp.write_text(size_s)
                    Path(tmp).replace(path / DU_SIZE_FILENAME)
                except OSError:
                    continue  # entry vanished mid-scan (e.g. experiment deleted)
                if path != data_dir:
                    logger.debug("du: %s = %s bytes", path.name, size_s)
            logger.info("Storage size updated: %d bytes", int((data_dir / DU_SIZE_FILENAME).read_text()))
        except Exception as e:
            stderr = getattr(e, "stderr", "") or ""
            logger.warning("du failed: %s%s", e, f" | stderr: {stderr.strip()}" if stderr.strip() else "")
        time.sleep(DU_INTERVAL)


def start_du_monitor(data_dir: Path, initial_delay: float = 0.0) -> None:
    """
    Start a daemon thread that measures data_dir size every DU_INTERVAL seconds.

    Args:
        data_dir: Directory to measure (DATA_DIR).
        initial_delay: Seconds to wait before first measurement.
    """
    if any(t.name == "du-monitor" for t in threading.enumerate()):
        logger.debug("du monitor thread already running, skipping")
        return

    thread = threading.Thread(
        target=_du_loop,
        args=(data_dir, initial_delay),
        daemon=True,
        name="du-monitor",
    )
    thread.start()
    logger.info("du monitor started (interval: %ds, initial delay: %.1fs)", DU_INTERVAL, initial_delay)


# Timeout for git clone operations (seconds)
GIT_CLONE_TIMEOUT = 120

# Matches the ``://userinfo@`` segment of a URL so captured git stderr can be scrubbed.
_URL_USERINFO_RE = re.compile(r"(://)[^@\s/]+(@)")


def download_git_repo(git_url: str, target_dir: Path, access_token: str | None = None) -> None:
    """Shallow-clone a git repository into ``target_dir`` (no subdirectory, no ``.git``)."""
    target_dir.mkdir(parents=True, exist_ok=True)
    clone_url = _inject_token(git_url, access_token)

    with tempfile.TemporaryDirectory() as tmp_dir:
        clone_dir = Path(tmp_dir) / "repo"
        _git(
            ["clone", "--depth", "1", "--single-branch", "--no-tags", "--", clone_url, str(clone_dir)],
            label="clone",
            secret=access_token,
        )

        git_dir = clone_dir / ".git"
        if git_dir.exists():
            shutil.rmtree(git_dir)

        _move_contents(clone_dir, target_dir)

        logger.info("Downloaded git repository from %s", git_url)


def _inject_token(git_url: str, access_token: str | None) -> str:
    """
    Inject an access token into an HTTPS git URL for cloning.

    Returns:
        The URL with the token embedded, or the original URL if no token applies.
    """
    if not access_token or git_url.startswith("git@"):
        return git_url
    parsed = urlparse(git_url)
    if parsed.scheme not in {"http", "https"}:
        return git_url
    return parsed._replace(netloc=f"{access_token}@{parsed.netloc}").geturl()


def _redact(text: str | None, secret: str | None) -> str:
    """
    Strip the literal secret and any ``://userinfo@`` segment from git output.

    Returns:
        The scrubbed text.
    """
    if not text:
        return ""
    if secret:
        text = text.replace(secret, "***")
    return _URL_USERINFO_RE.sub(r"\1***\2", text)


def _git(args: list[str], *, cwd: Path | None = None, label: str = "operation", secret: str | None = None) -> None:
    """
    Run a git subprocess, logging only the redacted stderr.

    Raises:
        InternalServerError: If the git command fails or times out.
    """
    try:
        subprocess.run(
            ["git", *args],
            check=True,
            capture_output=True,
            text=True,
            cwd=cwd,
            timeout=GIT_CLONE_TIMEOUT,
        )
    except subprocess.CalledProcessError as e:
        raw = e.stderr if isinstance(e.stderr, str) else ""
        detail = _redact((raw or str(e)).strip(), secret)
        logger.error("Git %s failed: %s", label, detail or "git operation failed")
        raise InternalServerError(description=f"Git {label} failed: {detail or 'git operation failed'}") from e
    except subprocess.TimeoutExpired as e:
        raise InternalServerError(description=f"Git {label} timed out after {GIT_CLONE_TIMEOUT}s") from e


def _is_partial_clone_unsupported(exc: BaseException) -> bool:
    """
    Return True when the clone failed because the server rejects partial-clone filtering.

    Returns:
        True for partial-clone failures, False for timeouts/auth/network errors.
    """
    cause = exc.__cause__
    if not isinstance(cause, subprocess.CalledProcessError):
        return False
    stderr = cause.stderr if isinstance(cause.stderr, str) else ""
    text = stderr.lower()
    return "filter" in text or "partial" in text


def _is_outside(path: Path, base: Path) -> bool:
    """
    Return True when ``path`` resolves outside ``base`` (e.g. a symlink escape).

    Returns:
        True if the path escapes the base directory.
    """
    try:
        path.resolve().relative_to(base.resolve())
    except ValueError:
        return True
    return False


def _move_contents(src_dir: Path, target_dir: Path) -> None:
    """Move every entry of ``src_dir`` into ``target_dir``, replacing existing entries."""
    for item in src_dir.iterdir():
        dest = target_dir / item.name
        if dest.exists():
            shutil.rmtree(dest) if dest.is_dir() else dest.unlink()
        shutil.move(item, dest)


def download_git_repo_module(git_url: str, module_path: str, target_dir: Path, access_token: str | None = None) -> None:
    """
    Sparse-checkout a single module subdirectory into ``target_dir``.

    Raises:
        NotFound: If ``module_path`` does not exist in the repository or escapes the clone.
        InternalServerError: If a git operation fails or times out.
    """
    target_dir.mkdir(parents=True, exist_ok=True)
    clone_url = _inject_token(git_url, access_token)

    with tempfile.TemporaryDirectory() as tmp_dir:
        clone_dir = Path(tmp_dir) / "repo"

        try:
            _git(
                [
                    "clone",
                    "--depth",
                    "1",
                    "--single-branch",
                    "--no-tags",
                    "--no-checkout",
                    "--filter=blob:none",
                    "--",
                    clone_url,
                    str(clone_dir),
                ],
                label="clone",
                secret=access_token,
            )
        except InternalServerError as exc:
            # Retry only on partial-clone-unsupported; surface all other failures.
            if not _is_partial_clone_unsupported(exc):
                raise
            shutil.rmtree(clone_dir, ignore_errors=True)
            _git(
                ["clone", "--depth", "1", "--single-branch", "--no-tags", "--", clone_url, str(clone_dir)],
                label="clone",
                secret=access_token,
            )

        # Configure sparse checkout for the selected module directory.
        _git(["sparse-checkout", "init", "--no-cone"], cwd=clone_dir, label="sparse-checkout init", secret=access_token)
        _git(["sparse-checkout", "set", module_path], cwd=clone_dir, label="sparse-checkout set", secret=access_token)
        _git(["checkout"], cwd=clone_dir, label="checkout", secret=access_token)

        # Reject symlink/traversal escapes before copying (could move other tenants' data).
        clone_root = clone_dir.resolve()
        module_dir = clone_dir / module_path
        if not module_dir.resolve().is_dir() or _is_outside(module_dir, clone_root):
            raise NotFound(description=f"Notebook module path '{module_path}' not found in repository.")

        _move_contents(module_dir, target_dir)

        logger.info("Downloaded notebook module '%s' from %s", module_path, git_url)
