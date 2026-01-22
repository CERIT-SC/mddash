import logging
import os
import random
import re
import shutil
import subprocess
import tempfile
from collections import deque
from pathlib import Path
from urllib.parse import urlparse

from werkzeug.exceptions import BadRequest, Forbidden, InternalServerError

logger = logging.getLogger(__name__)

LETTERS = "abcdefghijklmnopqrstuvwxyz"


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


def get_files_with_extensions(dir: Path, ext: str | list[str] | None = None) -> list[dict[str, object]]:
    """
    Get all files in a directory, optionally filtered by extension.

    Args:
        dir: Directory to search for files.
        ext: File extension(s) to filter by (e.g., 'txt', ['tpr', 'gro']).
             If None, returns all files.

    Returns:
        list[dict[str, object]]: List of dictionaries with file name and size.

    Raises:
        ValueError: If dir is not a directory.
    """
    if not dir.is_dir():
        raise ValueError(f"{dir} is not a directory")

    extensions = None
    if ext is not None:
        extensions = [e.lower() for e in ext] if isinstance(ext, list) else [ext.lower()]

    files = []

    for file in dir.iterdir():
        if not file.is_file():
            continue

        if extensions is None:
            files.append({"name": file.name, "size": file.stat().st_size})
        else:
            file_ext = file.suffix.lstrip(".").lower()
            if file_ext in extensions:
                files.append({"name": file.name, "size": file.stat().st_size})

    return files


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

    Walks the directory tree and sums up all file sizes. Uses os.scandir for fast iteration.

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

    total_size = 0

    for entry in os.scandir(path):
        if entry.is_file(follow_symlinks=False):
            total_size += entry.stat(follow_symlinks=False).st_size
        elif entry.is_dir(follow_symlinks=False):
            total_size += get_directory_size(entry.path)

    return total_size


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


def download_git_repo(git_url: str, target_dir: Path) -> None:
    """
    Download files from a git repository without history.

    Supports any git URL: GitHub, GitLab, Bitbucket, self-hosted, SSH, HTTPS.
    Files are placed directly in target_dir (no subdirectory, no .git folder).

    Args:
        git_url: Git repository URL (HTTPS or SSH).
        target_dir: Directory where files should be placed.

    Raises:
        BadRequest: If the git URL is invalid.
        InternalServerError: If git clone fails.
    """
    if not _is_valid_git_url(git_url):
        raise BadRequest(description=f"Invalid git URL: {git_url}")

    target_dir.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory() as tmp_dir:
        clone_dir = Path(tmp_dir) / "repo"

        try:
            _git_clone_shallow(git_url, clone_dir)
            _remove_git_directory(clone_dir)
            _move_contents(clone_dir, target_dir)
            logger.info(f"Downloaded git repository from {git_url}")

        except subprocess.CalledProcessError as e:
            error_msg = _parse_git_error(e.stderr)
            logger.error(f"Git clone failed: {error_msg}")
            raise InternalServerError(description=f"Failed to clone repository: {error_msg}")

        except subprocess.TimeoutExpired:
            raise InternalServerError(description=f"Git clone timed out after {GIT_CLONE_TIMEOUT}s")


def _is_valid_git_url(url: str) -> bool:
    """Validate git URL format (HTTPS or SSH)."""
    # SSH format: git@host:owner/repo.git
    if url.startswith("git@") and ":" in url:
        return True

    # HTTPS format
    try:
        parsed = urlparse(url)
        return parsed.scheme in ("http", "https") and bool(parsed.netloc)
    except Exception:
        return False


def _git_clone_shallow(git_url: str, clone_dir: Path) -> None:
    """Execute shallow git clone."""
    cmd = [
        "git",
        "clone",
        "--depth",
        "1",
        "--single-branch",
        git_url,
        str(clone_dir),
    ]

    subprocess.run(
        cmd,
        check=True,
        capture_output=True,
        text=True,
        timeout=GIT_CLONE_TIMEOUT,
    )


def _remove_git_directory(repo_dir: Path) -> None:
    """Remove .git directory from cloned repository."""
    git_dir = repo_dir / ".git"
    if git_dir.exists():
        shutil.rmtree(git_dir)


def _move_contents(source_dir: Path, target_dir: Path) -> None:
    """Move all contents from source to target directory."""
    for item in source_dir.iterdir():
        dest = target_dir / item.name
        # Overwrite existing files/dirs (notebooks take precedence)
        if dest.exists():
            if dest.is_dir():
                shutil.rmtree(dest)
            else:
                dest.unlink()
        shutil.move(str(item), str(dest))


def _parse_git_error(stderr: str) -> str:
    """Convert git stderr to user-friendly message."""
    stderr_lower = stderr.lower()

    if "could not find remote branch" in stderr_lower:
        return "Branch not found in repository"
    if "repository not found" in stderr_lower:
        return "Repository not found"
    if "authentication" in stderr_lower or "permission denied" in stderr_lower:
        return "Authentication required - private repository or invalid credentials"
    if "could not resolve host" in stderr_lower:
        return "Could not connect to git server"

    return stderr.strip() or "Unknown git error"
