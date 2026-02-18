import fnmatch
import logging
import os
import random
import re
import shutil
import subprocess
import tempfile
from collections import deque
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse

from cachetools import TTLCache
from werkzeug.exceptions import BadRequest, Forbidden, InternalServerError

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

# contains `pod_resources` and `directory_size` keys to cache metrics.
metrics_cache: TTLCache = TTLCache(maxsize=2, ttl=120)


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


def find_file(dir: Path, filename: str) -> Path | None:
    """
    Find a file by name in a directory tree.

    Args:
        dir: Directory to search.
        filename: Name of the file to find.

    Returns:
        Path to the file if found, None otherwise.
    """
    if not dir.is_dir():
        return None

    for item in dir.iterdir():
        if is_excluded_path(item, dir):
            continue

        if item.is_file() and item.name == filename:
            return item
        if item.is_dir():
            result = find_file(item, filename)
            if result:
                return result

    return None


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

    Raises:
        FileNotFoundError: If the file does not exist.
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


def get_directory_size(path: Path | str) -> int:
    """
    Calculate total size of a directory in bytes.

    Uses the `du` command for fast directory traversal.

    Args:
        path: Path to the directory.

    Returns:
        int: Total size in bytes.

    Raises:
        FileNotFoundError: If the path does not exist.
        NotADirectoryError: If the path is not a directory.
    """
    path = Path(path) if isinstance(path, str) else path

    if not path.exists():
        raise FileNotFoundError(f"{path} does not exist")

    if not path.is_dir():
        raise NotADirectoryError(f"{path} is not a directory")

    result = subprocess.run(
        ["du", "-sb", str(path)],
        capture_output=True,
        text=True,
        check=True,
        timeout=120,
    )
    size_str = result.stdout.split()[0]
    return int(size_str)


def check_experiment_id(experiment_id: str) -> None:
    """
    Validate that an experiment ID is a 5-character lowercase string.

    Args:
        experiment_id: The experiment ID to validate.

    Raises:
        BadRequest: If the ID format is invalid.
    """
    if not experiment_id or not re.match(r"^[a-z]{5}$", experiment_id):
        raise BadRequest("Invalid experiment ID format.")


def check_filename(filename: str, allowed_extensions: list[str] | None = None) -> None:
    """
    Validate a filename for security and optional extension restrictions.

    Args:
        filename: The filename to validate.
        allowed_extensions: Optional list of allowed file extensions (without dots).

    Raises:
        BadRequest: If the filename is invalid or extension not allowed.
    """
    if not filename:
        raise BadRequest("Filename cannot be empty.")

    if ".." in filename or "/" in filename or "\\" in filename:
        raise BadRequest("Invalid filename: path traversal not allowed.")

    if filename.startswith(".") or filename.startswith("~"):
        raise BadRequest("Invalid filename: hidden files not allowed.")

    if "\0" in filename:
        raise BadRequest("Invalid filename: null bytes not allowed.")

    if allowed_extensions:
        file_ext = Path(filename).suffix.lstrip(".").lower()
        if not file_ext or file_ext not in allowed_extensions:
            raise BadRequest(f"Invalid file extension. Allowed: {', '.join(allowed_extensions)}")


def check_path(path: str, base_dir: Path) -> None:
    """
    Validate a path is safe and within the allowed base directory.

    Args:
        path: The relative path to validate.
        base_dir: The base directory the path must stay within.

    Raises:
        BadRequest: If the path is invalid.
        Forbidden: If path traversal is detected.
    """
    if not path:
        raise BadRequest("Path cannot be empty.")

    if "\0" in path:
        raise BadRequest("Invalid path: null bytes not allowed.")

    try:
        full_path = (base_dir / path).resolve()
        base_resolved = base_dir.resolve()

        if not str(full_path).startswith(str(base_resolved)):
            raise Forbidden("Path traversal not allowed.")
    except (ValueError, OSError):
        raise BadRequest("Invalid path.")


def check_log_type(log_type: str) -> None:
    """
    Validate that log_type is one of the allowed values.

    Args:
        log_type: The log type to validate ('gmx', 'stdout', or 'stderr').

    Raises:
        BadRequest: If the log type is invalid.
    """
    if log_type not in ["gmx", "stdout", "stderr"]:
        raise BadRequest("Invalid log type. Use 'gmx', 'stdout', or 'stderr'.")


def check_positive_int(value: str, param_name: str = "value", max_value: int | None = None) -> None:
    """
    Validate that a string represents a positive integer within bounds.

    Args:
        value: The string value to validate.
        param_name: Name of the parameter for error messages.
        max_value: Optional maximum allowed value.

    Raises:
        BadRequest: If the value is not a valid positive integer or exceeds max.
    """
    if not value.isdigit():
        raise BadRequest(f"{param_name} must be a positive integer.")

    int_value = int(value)
    if int_value <= 0:
        raise BadRequest(f"{param_name} must be greater than 0.")

    if max_value and int_value > max_value:
        raise BadRequest(f"{param_name} must not exceed {max_value}.")


# Timeout for git clone operations (seconds)
GIT_CLONE_TIMEOUT = 120


def validate_git_url(git_url: str) -> None:
    """
    Validate git URL for safety.

    Rejects unsafe URL patterns: credentials, local paths, file://, option injection.

    Raises:
        BadRequest: If URL is invalid or unsafe.
    """
    if not git_url or not git_url.strip():
        raise BadRequest("Git URL cannot be empty.")

    url = git_url.strip()

    # Reject option injection, local paths, file:// URLs
    if url.startswith("-") or url.startswith("/") or url.startswith("."):
        raise BadRequest("Invalid git URL format.")
    if url.lower().startswith("file://"):
        raise BadRequest("file:// URLs are not allowed.")

    # SSH format: git@host:owner/repo.git - valid
    if url.startswith("git@") and ":" in url:
        return

    # HTTPS/HTTP URLs
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        raise BadRequest("Only http://, https://, or git@ URLs are allowed.")
    if parsed.username or parsed.password:
        raise BadRequest("URLs with embedded credentials are not allowed.")
    if not parsed.netloc:
        raise BadRequest("Invalid git URL: missing host.")


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
        if parsed.scheme in ("http", "https"):
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
