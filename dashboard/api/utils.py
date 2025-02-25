import random

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


if __name__ == '__main__':
    print(get_unique_id())
