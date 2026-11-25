"""
`mddash-run-notebook`: execute a setup notebook headless and report progress in a status doc.

The dashboard API polls the doc; the notebook keeps its outputs so JupyterLab shows where a run stopped.
"""

import argparse
import contextlib
import json
import os
import sys
import tempfile
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import nbformat
from nbclient import NotebookClient
from nbclient.exceptions import CellExecutionError

from jupyterlab_pipeline_tracker.discovery import discover_steps

MANIFEST_SUFFIX = ".simulation.json"
EVALUE_LIMIT = 500


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _atomic_write(path: Path, text: str) -> None:
    """Temp file plus rename, so a reader never sees a torn file."""
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        Path(tmp).replace(path)
    except BaseException:
        with contextlib.suppress(OSError):
            Path(tmp).unlink()
        raise


def _manifests_since(root: Path, since: float) -> list[str]:
    """Manifests (root-relative) written during the run; hidden dirs such as `.binder-env` are skipped."""
    found = []
    for directory, dirs, files in os.walk(root):
        dirs[:] = sorted(d for d in dirs if not d.startswith("."))
        for name in sorted(files):
            path = Path(directory) / name
            if name.endswith(MANIFEST_SUFFIX) and path.stat().st_mtime >= since:
                found.append(path.relative_to(root).as_posix())
    return found


class _Status:
    def __init__(self, path: Path, total: int) -> None:
        self.path = path
        self.doc: dict[str, Any] = {
            "state": "running",
            "step": 0,
            "total": total,
            "title": None,
            "started_at": _now(),
            "finished_at": None,
            "manifests": [],
            "error": None,
        }

    def update(self, **fields: Any) -> None:  # ruff:ignore[any-type]
        self.doc.update(fields)
        _atomic_write(self.path, json.dumps(self.doc, indent=2))


def run(notebook_path: Path, status_path: Path, root: Path) -> int:
    """Execute every cell in order; returns the process exit code."""
    notebook = nbformat.read(notebook_path, as_version=4)
    steps = discover_steps(notebook)
    step_of_cell = {cell: number for number, step in enumerate(steps, start=1) for cell in step.cell_indices}
    status = _Status(status_path, len(steps))
    status.update()
    # mtime resolution on network filesystems is coarse; a manifest touched in the same second still counts.
    started = time.time() - 1

    client = NotebookClient(notebook, timeout=None, resources={"metadata": {"path": str(notebook_path.parent)}})
    step = 0
    try:
        with client.setup_kernel():
            for index, cell in enumerate(notebook.cells):
                if cell.cell_type != "code":
                    continue
                if (number := step_of_cell.get(index)) is not None and number != step:
                    step = number
                    status.update(step=step, title=steps[step - 1].label)
                try:
                    client.execute_cell(cell, index)
                finally:
                    _atomic_write(notebook_path, nbformat.writes(notebook))
    except CellExecutionError as exc:
        status.update(
            state="failed",
            finished_at=_now(),
            manifests=_manifests_since(root, started),
            error={
                "step": step or None,
                "cell": index,
                "ename": exc.ename,
                "evalue": (exc.evalue or "")[:EVALUE_LIMIT],
            },
        )
        return 1
    status.update(state="done", finished_at=_now(), manifests=_manifests_since(root, started))
    return 0


def main(argv: list[str] | None = None) -> int:
    """CLI entry point."""
    parser = argparse.ArgumentParser(prog="mddash-run-notebook", description=__doc__)
    parser.add_argument("notebook", type=Path, help="Notebook to execute, relative to --root")
    parser.add_argument("--status", type=Path, required=True, help="Status doc path, relative to --root")
    parser.add_argument("--root", type=Path, default=Path.cwd(), help="Experiment directory (default: cwd)")
    args = parser.parse_args(argv)
    root = args.root.resolve()
    return run(root / args.notebook, root / args.status, root)


if __name__ == "__main__":
    sys.exit(main())
