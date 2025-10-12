import os
import random
from collections import deque
from pathlib import Path


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


def get_files_with_extension(dir: Path, ext: str | list[str]) -> list[dict[str, object]]:
    '''
    Get all files in a directory with a specific extension.

    :param dir: Directory to search for files.
    :param ext: File extension to filter by (e.g., 'txt', 'tpr').
    :return: List of dictionaries with file name, and size.
    '''
    ext = [e.lower() for e in ext] if isinstance(ext, list) else [ext.lower()]
    files = []

    if not dir.is_dir():
        raise ValueError(f'{dir} is not a directory')

    for file in dir.iterdir():
        if not file.is_file():
            continue

        file_lower = file.name.lower()
        for e in ext:
            if file_lower.endswith(f'.{e}'):
                files.append({
                    'name': file.name,
                    'size': file.stat().st_size
                })
                break  # Avoid duplicate entries

    return files


def tail(file: Path | str, n: int = 10) -> str:
    '''
    Read last n lines of a file. It works efficiently for large files by reading chunks from the end.

    :param file: Path to the file.
    :param n: Number of lines to read from the end of the file.
    :return: Last n lines of the file as a string.
    :raises FileNotFoundError: If the file does not exist.
    '''

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


if __name__ == '__main__':
    file = Path(__file__).parent / '_demo.py'
    print(tail(file, 10))
