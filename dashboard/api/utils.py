import fnmatch
import logging
import os
import random
import shutil
import subprocess
import tempfile
import threading
import time
from collections import deque
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse

from werkzeug.exceptions import InternalServerError

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
    "*.fit.xtc",
    "*.tpr",
    "*.cpt",
    "*.gro",
    "*.log",
]

EXCLUDED_FILES: list[str] = [
    "#*#",
    "*.swp",
    "*.tmp",
    ".nfs*",
    ".binder-env-installed",
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


def _du_loop(data_dir: Path) -> None:
    """Background thread body: measure data_dir size every DU_INTERVAL seconds."""
    size_file = data_dir / DU_SIZE_FILENAME
    while True:
        try:
            result = subprocess.run(
                ["du", "-sb", str(data_dir)],
                capture_output=True,
                text=True,
                check=True,
            )
            size = int(result.stdout.split()[0])
            size_file.write_text(str(size))
            logger.info("Storage size updated: %d bytes", size)
        except Exception as e:
            stderr = getattr(e, "stderr", "") or ""
            logger.warning("du failed: %s%s", e, f" | stderr: {stderr.strip()}" if stderr.strip() else "")
        time.sleep(DU_INTERVAL)


def start_du_monitor(data_dir: Path) -> None:
    """
    Start a daemon thread that measures data_dir size every DU_INTERVAL seconds.

    Args:
        data_dir: Directory to measure (DATA_DIR).
    """
    if any(t.name == "du-monitor" for t in threading.enumerate()):
        logger.debug("du monitor thread already running, skipping")
        return

    thread = threading.Thread(
        target=_du_loop,
        args=(data_dir,),
        daemon=True,
        name="du-monitor",
    )
    thread.start()
    logger.info("du monitor started (interval: %ds)", DU_INTERVAL)


# Timeout for git clone operations (seconds)
GIT_CLONE_TIMEOUT = 120


def download_git_repo(git_url: str, target_dir: Path, access_token: str | None = None) -> None:
    """
    Download files from a git repository without history.

    Files are placed directly in target_dir (no subdirectory, no .git folder).
    Caller is responsible for validating the URL before calling this function.

    Args:
        git_url: Git repository URL to clone.
        target_dir: Directory to download files to.
        access_token: Optional access token for private HTTPS repositories.
                      Not applicable to SSH URLs (git@...).

    Raises:
        InternalServerError: If git clone fails.
    """
    target_dir.mkdir(parents=True, exist_ok=True)

    # Inject token into HTTPS URLs
    clone_url = git_url
    if access_token and not git_url.startswith("git@"):
        # Parse and reconstruct URL with token
        parsed = urlparse(git_url)
        if parsed.scheme in {"http", "https"}:
            # Construct authenticated URL: https://token@host/path
            netloc_with_token = f"{access_token}@{parsed.netloc}"
            clone_url = parsed._replace(netloc=netloc_with_token).geturl()

    with tempfile.TemporaryDirectory() as tmp_dir:
        clone_dir = Path(tmp_dir) / "repo"

        try:
            subprocess.run(
                ["git", "clone", "--depth", "1", "--single-branch", "--no-tags", "--", clone_url, str(clone_dir)],
                check=True,
                capture_output=True,
                text=True,
                timeout=GIT_CLONE_TIMEOUT,
            )

            git_dir = clone_dir / ".git"
            if git_dir.exists():
                shutil.rmtree(git_dir)

            for item in clone_dir.iterdir():
                dest = target_dir / item.name
                if dest.exists():
                    shutil.rmtree(dest) if dest.is_dir() else dest.unlink()
                shutil.move(item, dest)

            logger.info("Downloaded git repository from %s", git_url)

        except subprocess.CalledProcessError as e:
            stderr = (e.stderr or "").strip() if isinstance(e.stderr, str) else str(e).strip()
            logger.error("Git clone failed: %s", stderr or str(e))
            raise InternalServerError(description=f"Failed to clone repository: {stderr or 'git clone failed'}")

        except subprocess.TimeoutExpired:
            raise InternalServerError(description=f"Git clone timed out after {GIT_CLONE_TIMEOUT}s")
