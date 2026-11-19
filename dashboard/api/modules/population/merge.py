"""Safe same-filesystem merge of a staged Datahugger dataset into a prepared experiment directory."""

import contextlib
import logging
from pathlib import Path

logger = logging.getLogger(__name__)


class PopulationMergeError(Exception):
    """Stable user-safe merge failure; the raw detail is only logged server-side."""


def merge_staged(staging_dir: Path, experiment_dir: Path) -> None:
    """
    Move every staged file into `experiment_dir`, preserving relative paths (no dataset wrapper).

    The whole staged tree is validated first (unsafe paths, symlinks, special files, and
    file/directory conflicts with the prepared notebooks are rejected); compatible directory
    overlap merges. Valid content moves by same-filesystem rename without copying.

    Raises:
        PopulationMergeError: With a stable user-safe message.
    """
    if not staging_dir.is_dir() or not any(staging_dir.iterdir()):
        raise PopulationMergeError("The downloaded repository is missing or empty.")
    _validate_tree(staging_dir, staging_dir)
    try:
        _move_tree(staging_dir, experiment_dir)
    except PopulationMergeError:
        raise
    except OSError:
        logger.exception("Population merge of %s into %s failed", staging_dir, experiment_dir)
        raise PopulationMergeError("The repository content could not be moved into the experiment.") from None


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


def _move_tree(src: Path, dst: Path, prefix: str = "") -> None:
    """Rename staged entries into place, mirroring names level by level; recurse where directories overlap."""
    for entry in sorted(src.iterdir(), key=lambda p: p.name):
        rel = entry.name if not prefix else f"{prefix}/{entry.name}"
        target = dst / entry.name
        if target.exists() or target.is_symlink():
            if entry.is_dir() and target.is_dir() and not target.is_symlink():
                _move_tree(entry, target, rel)
                # Drained overlap: remove the now-empty source dir (a no-op when content remained).
                with contextlib.suppress(OSError):
                    entry.rmdir()
                continue
            # The experiment directory cannot change between validation and move;
            # a conflict here would mean the plan was stale.
            raise PopulationMergeError(f"The repository content collides with the experiment at '{rel}'.")
        Path(entry).rename(target)
