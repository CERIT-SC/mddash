import asyncio
import fnmatch
import logging
import os
import random
import re
import subprocess
import unicodedata
from collections import deque
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import quote

import anyio

logger = logging.getLogger(__name__)

LETTERS = "abcdefghijklmnopqrstuvwxyz"

EXCLUDED_DIRS: list[str] = [
    ".ipynb_checkpoints",
    "__pycache__",
    ".cache",
    ".local",
    ".config",
    ".jupyter",
    ".git",
    ".binder-env",
    "*.edr",
    "*.xtc",
    "*.tpr",
    "*.cpt",
    "*.gro",
    "*.log",
    "analysis/mwf",
]

EXCLUDED_FILES: list[str] = [
    "#*#",
    "*.swp",
    "*.tmp",
    ".gitkeep",
    ".nfs*",
    ".binder-env-installed",
    "inputs.yaml",
    ".storage_size",
    ".storage_size.tmp*",
]


@dataclass
class FileEntry:
    """Data class representing a file with its name, size, and relative path."""

    name: str
    size: int
    path: str


def file_download_url(experiment_id: str, path: str) -> str:
    """Build the API download URL for an experiment file; each path segment is percent-encoded."""
    from core.config import API_PREFIX  # ruff:ignore[import-outside-top-level]

    quoted = "/".join(quote(part) for part in Path(path).parts if part)
    return f"{API_PREFIX}/experiments/{experiment_id}/files/{quoted}"


def generate_id(length: int = 5) -> str:
    """Generate a random lowercase alphabetic ID."""
    return "".join(random.choice(LETTERS) for _ in range(length))


def get_unique_id(id_dir: Path) -> str:
    """
    Generate a unique ID that doesn't exist in the given directory.

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


def get_files_with_extensions(
    dir: Path, ext: str | list[str] | None = None, base_dir: Path | None = None
) -> list[FileEntry]:
    """
    Get all files in a directory, optionally filtered by extension.

    Raises:
        ValueError: If dir is not a directory.
    """
    if not dir.is_dir():
        raise ValueError(f"{dir} is not a directory")

    if base_dir is None:
        base_dir = dir

    extensions = None
    if ext is not None:
        extensions = [e.lower() for e in ext] if isinstance(ext, list) else [ext.lower()]

    files = []

    for item in dir.iterdir():
        if is_excluded_path(item, base_dir):
            continue

        if item.is_file():
            relative_path = str(item.relative_to(base_dir))
            if extensions is None:
                files.append(FileEntry(name=item.name, size=item.stat().st_size, path=relative_path))
            else:
                file_ext = item.suffix.lstrip(".").lower()
                if file_ext in extensions:
                    files.append(FileEntry(name=item.name, size=item.stat().st_size, path=relative_path))
        elif item.is_dir():
            files.extend(get_files_with_extensions(item, ext, base_dir))

    return files


_NSTEPS_RE = re.compile(r"-nsteps(?:=|\s+)['\"]?(\d+)")
_NSTEPS_ARG_RE = re.compile(r"-nsteps(?:=|\s+)['\"]?\d+['\"]?")
_CPI_ARG_RE = re.compile(r"-cpi(?:[=\s]|$)")


def nsteps_override(extra_args: str) -> int | None:
    """Extract the effective GROMACS ``-nsteps`` override from extra_args (last occurrence wins), or None."""
    value = int(matches[-1]) if (matches := _NSTEPS_RE.findall(extra_args or "")) else 0
    return value if value > 0 else None


def strip_run_control_args(extra_args: str) -> str:
    """
    Return extra_args with GROMACS run-control flags removed; whitespace-normalized.

    ``-nsteps`` is dropped (the extend flow re-adds its delta: ``mdrun -cpi`` counts additional steps);
    ``-cpi`` raises ``ValueError``.
    """
    if _CPI_ARG_RE.search(extra_args or ""):
        raise ValueError(
            "Simulation extra_args must not contain '-cpi'; checkpoint input is managed by the extend flow."
        )
    return " ".join(_NSTEPS_ARG_RE.sub("", extra_args or "").split())


def is_excluded_path(path: Path, base_dir: Path) -> bool:
    """Determine whether a path should be excluded from uploads."""
    try:
        relative_path = path.relative_to(base_dir)
    except ValueError:
        relative_path = path

    dir_parts = relative_path.parts if path.is_dir() else relative_path.parts[:-1]

    if any(fnmatch.fnmatch(part, pattern) for part in dir_parts for pattern in EXCLUDED_DIRS):
        return True

    return any(fnmatch.fnmatch(path.name, pattern) for pattern in EXCLUDED_FILES)


def count_lines(file: Path | str, chunk_size: int = 1024 * 1024) -> int | None:
    """
    Count newline-terminated lines (``wc -l`` semantics) without loading the file.

    The last, possibly unterminated line of a still-growing log is deliberately
    not counted until its newline lands.
    """
    file_path = Path(file) if isinstance(file, str) else file
    try:
        count = 0
        with file_path.open("rb") as f:
            while chunk := f.read(chunk_size):
                count += chunk.count(b"\n")
        return count
    except OSError:
        return None


def tail(file: Path | str, n: int = 10) -> str:
    """Read last n lines of a file efficiently by reading chunks from the end."""
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


_TAIL_BUDGET_BYTES = 65536


def tail_bytes(file: Path | str, budget: int = _TAIL_BUDGET_BYTES) -> str:
    """
    Read the last ``budget`` bytes of a file as text (first partial line dropped).

    A byte budget, not a line window: engine trailers span hundreds of lines,
    pushing markers past any fixed line count.
    """
    file_path = Path(file) if isinstance(file, str) else file
    size = file_path.stat().st_size
    with file_path.open("rb") as f:
        f.seek(max(0, size - budget))
        data = f.read()
    text = data.decode("utf-8", errors="replace")
    if size > budget and "\n" in text:
        text = text.split("\n", 1)[1]
    return text


DU_SIZE_FILENAME = ".storage_size"
DU_INTERVAL = 30 * 60  # 30 minutes


def get_du_size(data_dir: Path) -> int | None:
    """Read the last measured storage size of data_dir."""
    try:
        return int((data_dir / DU_SIZE_FILENAME).read_text().strip())
    except Exception:
        return None


def _store_du_sizes(data_dir: Path, du_output: str) -> None:
    """Write `du -b --max-depth=1` sizes into per-directory marker files."""
    for line in du_output.splitlines():
        size_s, _, path_s = line.rstrip("/").partition("\t")
        path = Path(path_s)
        # A marker can only live inside a directory: skip top-level files,
        # and skip hidden dirs (.rclone-bisync, .ipynb_checkpoints) entirely.
        if path != data_dir and (path.name.startswith(".") or not path.is_dir()):
            continue
        try:
            # atomic: a reader must never see a half-written marker
            tmp = path / f"{DU_SIZE_FILENAME}.tmp{os.getpid()}"
            tmp.write_text(size_s)
            Path(tmp).replace(path / DU_SIZE_FILENAME)
        except OSError:
            continue  # entry vanished mid-scan (e.g. experiment deleted)
        if path != data_dir:
            logger.debug("du: %s = %s bytes", path.name, size_s)
    logger.info("Storage size updated: %d bytes", int((data_dir / DU_SIZE_FILENAME).read_text()))


async def _measure_du(data_dir: Path) -> None:
    # --max-depth=1 reports each entry inside data_dir plus the total in one pass
    proc = await asyncio.create_subprocess_exec(
        "du", "-b", "--max-depth=1", str(data_dir), stdout=subprocess.PIPE, stderr=subprocess.PIPE
    )
    stdout, stderr = await proc.communicate()
    if proc.returncode != 0:
        raise subprocess.CalledProcessError(proc.returncode or 1, "du", stdout, stderr.decode(errors="replace"))
    await anyio.to_thread.run_sync(_store_du_sizes, data_dir, stdout.decode(errors="replace"))


async def du_monitor(data_dir: Path, initial_delay: float = 0.0) -> None:
    """Measure data_dir and per-experiment sizes every DU_INTERVAL seconds (run as a background task)."""
    if initial_delay > 0:
        await asyncio.sleep(initial_delay)
    while True:
        try:
            await _measure_du(data_dir)
        except Exception as e:
            stderr = getattr(e, "stderr", "") or ""
            logger.warning("du failed: %s%s", e, f" | stderr: {stderr.strip()}" if stderr.strip() else "")
        await asyncio.sleep(DU_INTERVAL)


_FILENAME_STRIP_RE = re.compile(r"[^A-Za-z0-9_.-]")


def secure_filename(filename: str) -> str:
    """ASCII-only, separator-free version of an uploaded file name (werkzeug's algorithm); may be empty."""
    filename = unicodedata.normalize("NFKD", filename).encode("ascii", "ignore").decode("ascii")
    for sep in (os.sep, os.path.altsep):
        if sep:
            filename = filename.replace(sep, " ")
    return _FILENAME_STRIP_RE.sub("", "_".join(filename.split())).strip("._")
