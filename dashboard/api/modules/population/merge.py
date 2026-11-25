"""Safe same-filesystem merge of a staged Datahugger dataset into a prepared experiment directory."""

import contextlib
import logging
from pathlib import Path

logger = logging.getLogger(__name__)


class PopulationMergeError(Exception):
    """Stable user-safe merge failure; the raw detail is only logged server-side."""


def merge_staged(staging_dir: Path, experiment_dir: Path) -> list[str]:
    """
    Move every staged file into `experiment_dir`, preserving relative paths (no dataset wrapper).

    The whole staged tree is validated first (unsafe paths, symlinks, and special files are
    rejected); directory overlap merges. A staged entry whose name the notebooks already use
    keeps both: the dataset copy is renamed (`README.md` -> `README.dataset.md`). Valid content
    moves by same-filesystem rename without copying.

    Returns:
        Experiment-relative paths of the renamed dataset entries.

    Raises:
        PopulationMergeError: With a stable user-safe message.
    """
    if not staging_dir.is_dir() or not any(staging_dir.iterdir()):
        raise PopulationMergeError("The downloaded repository is missing or empty.")
    _validate_tree(staging_dir, staging_dir)
    renamed: list[str] = []
    try:
        _move_tree(staging_dir, experiment_dir, renamed)
    except OSError:
        logger.exception("Population merge of %s into %s failed", staging_dir, experiment_dir)
        raise PopulationMergeError("The repository content could not be moved into the experiment.") from None
    return renamed


def _validate_tree(src: Path, root: Path) -> None:
    """Reject symlinks, special files, and traversal paths anywhere in the staged tree."""
    for entry in sorted(src.iterdir(), key=lambda p: p.name):
        rel = entry.relative_to(root)
        if ".." in rel.parts:
            raise PopulationMergeError(f"The repository content contains an unsafe path ('{rel}').")
        if entry.is_symlink():
            raise PopulationMergeError(f"Symlinks are not allowed in repository content ('{rel}').")
        if entry.is_dir():
            _validate_tree(entry, root)
        elif not entry.is_file():
            raise PopulationMergeError(f"Special files are not allowed in repository content ('{rel}').")


def _move_tree(src: Path, dst: Path, renamed: list[str], prefix: str = "") -> None:
    """Rename staged entries into place level by level; recurse where directories overlap."""
    for entry in sorted(src.iterdir(), key=lambda p: p.name):
        target = dst / entry.name
        if _exists(target):
            if entry.is_dir() and target.is_dir() and not target.is_symlink():
                _move_tree(entry, target, renamed, f"{prefix}{entry.name}/")
                # Drained overlap: remove the now-empty source dir (a no-op when content remained).
                with contextlib.suppress(OSError):
                    entry.rmdir()
                continue
            target = _free_name(dst, entry.name)
            renamed.append(f"{prefix}{target.name}")
        entry.rename(target)


def _exists(path: Path) -> bool:
    return path.exists() or path.is_symlink()


def _free_name(dst: Path, name: str) -> Path:
    """`README.md` -> `README.dataset.md`, then `README.dataset-2.md`, ... until unused."""
    stem, dot, suffix = name.rpartition(".")
    if not stem:  # no extension, or a dotfile such as `.gitignore`
        stem, dot, suffix = name, "", ""
    tag, n = "dataset", 1
    while _exists(candidate := dst / f"{stem}.{tag}{dot}{suffix}"):
        n += 1
        tag = f"dataset-{n}"
    return candidate
