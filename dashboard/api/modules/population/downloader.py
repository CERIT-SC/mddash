"""Pinned Datahugger-NG binding boundary (datahugger-ng==0.6.9)."""

from pathlib import Path

# Fixed download concurrency; the binding's zero/unlimited default must not be used.
DOWNLOAD_CONCURRENCY = 4


def download_dataset(repo_url: str, dst_dir: Path) -> int:
    """
    Resolve the public repository and download its full contents into `dst_dir` with validation.

    Blocking: the binding runs its own runtime and the worker performs it as the whole Job.
    Native resolution or download failures propagate to the worker, which records a
    sanitized receipt error; raw details never leave the worker.
    """
    # Imported lazily so tests can fake the pinned binding without the native package.
    from datahugger import resolve  # ruff:ignore[import-outside-top-level]

    dataset = resolve(repo_url)
    return dataset.download_with_validation(dst_dir=dst_dir, limit=DOWNLOAD_CONCURRENCY)
