import os
import re
import random
from collections import deque
from pathlib import Path
from werkzeug.exceptions import BadRequest, Forbidden


LETTERS = 'abcdefghijklmnopqrstuvwxyz'


def generate_id(length: int = 5) -> str:
    return ''.join(random.choice(LETTERS) for _ in range(length))


def get_unique_id(id_dir: Path) -> str:
    id_length = 5
    id = generate_id(id_length)

    iters = 0
    max_iters = 10_000_000  # 26^5 = 11,881,376

    while (id_dir / id).exists():
        id = generate_id(id_length)

        iters += 1
        if iters > max_iters:
            raise ValueError('You have too many experiments!')

    return id


def get_files_with_extensions(dir: Path, ext: str | list[str] | None = None) -> list[dict[str, object]]:
    """Get all files in a directory, optionally filtered by extension.

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
        raise ValueError(f'{dir} is not a directory')

    extensions = None
    if ext is not None:
        extensions = [e.lower() for e in ext] if isinstance(ext, list) else [ext.lower()]

    files = []

    for file in dir.iterdir():
        if not file.is_file():
            continue

        if extensions is None:
            files.append({
                'name': file.name,
                'size': file.stat().st_size
            })
        else:
            file_ext = file.suffix.lstrip('.').lower()
            if file_ext in extensions:
                files.append({
                    'name': file.name,
                    'size': file.stat().st_size
                })

    return files


def tail(file: Path | str, n: int = 10) -> str:
    """Read last n lines of a file efficiently by reading chunks from the end.

    Args:
        file: Path to the file.
        n: Number of lines to read from the end of the file.
    Returns:
        str: Last n lines of the file as a string.
    Raises:
        FileNotFoundError: If the file does not exist.
    """

    with open(file, 'rb') as f:
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

            chunk_lines = chunk.split(b'\n')

            # handle partial line at the end of the chunk
            if lines_found and chunk_lines:
                lines_found[0] = chunk_lines.pop() + lines_found[0]

            # Prepend newly read lines to the deque
            lines_found.extendleft(reversed(chunk_lines))

            pos = chunk_start

        result_lines = list(lines_found)[-n:]
        return b'\n'.join(result_lines).decode('utf-8', 'replace')


def get_directory_size(path: Path | str) -> int:
    """Calculate total size of a directory in bytes.

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
        raise FileNotFoundError(f'{path} does not exist')

    if not path.is_dir():
        raise NotADirectoryError(f'{path} is not a directory')

    total_size = 0

    for entry in os.scandir(path):
        if entry.is_file(follow_symlinks=False):
            total_size += entry.stat(follow_symlinks=False).st_size
        elif entry.is_dir(follow_symlinks=False):
            total_size += get_directory_size(entry.path)

    return total_size


def check_experiment_id(experiment_id: str) -> None:
    if not experiment_id or not re.match(r'^[a-z]{5}$', experiment_id):
        raise BadRequest('Invalid experiment ID format.')


def check_filename(filename: str, allowed_extensions: list[str] | None = None) -> None:
    if not filename:
        raise BadRequest('Filename cannot be empty.')

    if '..' in filename or '/' in filename or '\\' in filename:
        raise BadRequest('Invalid filename: path traversal not allowed.')

    if filename.startswith('.') or filename.startswith('~'):
        raise BadRequest('Invalid filename: hidden files not allowed.')

    if '\0' in filename:
        raise BadRequest('Invalid filename: null bytes not allowed.')

    if allowed_extensions:
        file_ext = Path(filename).suffix.lstrip('.').lower()
        if not file_ext or file_ext not in allowed_extensions:
            raise BadRequest(f'Invalid file extension. Allowed: {", ".join(allowed_extensions)}')


def check_path(path: str, base_dir: Path) -> None:
    if not path:
        raise BadRequest('Path cannot be empty.')

    if '\0' in path:
        raise BadRequest('Invalid path: null bytes not allowed.')

    try:
        full_path = (base_dir / path).resolve()
        base_resolved = base_dir.resolve()
        
        if not str(full_path).startswith(str(base_resolved)):
            raise Forbidden('Path traversal not allowed.')
    except (ValueError, OSError):
        raise BadRequest('Invalid path.')


def check_log_type(log_type: str) -> None:
    if log_type not in ['gmx', 'stdout', 'stderr']:
        raise BadRequest("Invalid log type. Use 'gmx', 'stdout', or 'stderr'.")


def check_positive_int(value: str, param_name: str = 'value', max_value: int | None = None) -> None:
    if not value.isdigit():
        raise BadRequest(f'{param_name} must be a positive integer.')

    int_value = int(value)
    if int_value <= 0:
        raise BadRequest(f'{param_name} must be greater than 0.')

    if max_value and int_value > max_value:
        raise BadRequest(f'{param_name} must not exceed {max_value}.')
