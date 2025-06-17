import random
from pathlib import Path

from config import DATA_DIR


LETTERS = 'abcdefghijklmnopqrstuvwxyz'


def generate_id(length: int = 5) -> str:
    return ''.join(random.choice(LETTERS) for _ in range(length))


def get_unique_id() -> str:
    id_length = 5
    id = generate_id(id_length)

    iters = 0
    max_iters = 10_000_000  # 26^5 = 11,881,376

    while (DATA_DIR / id).exists():
        id = generate_id(id_length)

        iters += 1
        if iters > max_iters:
            raise ValueError('You have too many experiments!')

    return id


def get_files_with_extension(dir: Path, ext: str) -> list[dict[str, any]]:
    '''
    Get all files in a directory with a specific extension.

    :param dir: Directory to search for files.
    :param ext: File extension to filter by (e.g., 'txt', 'tpr').
    :return: List of dictionaries with file name, and size.
    '''
    ext = ext.lower()
    files = []

    for file_path in dir.iterdir():
        if not file_path.is_file() or ext and not file_path.name.lower().endswith(f'.{ext}'):
            continue

        files.append({
            'name': file_path.name,
            'size': file_path.stat().st_size
        })
    
    return files


if __name__ == '__main__':
    print(get_unique_id())
