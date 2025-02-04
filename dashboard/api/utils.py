import random

from config import DATA_DIR


LETTERS = 'abcdefghijklmnopqrstuvwxyz'

def generate_id(length: int = 5) -> str:
    return ''.join(random.choice(LETTERS) for _ in range(length))

def get_unique_id() -> str:
    id = generate_id()
    while (DATA_DIR / id).exists():
        id = generate_id()
    return id


if __name__ == '__main__':
    print(get_unique_id())
