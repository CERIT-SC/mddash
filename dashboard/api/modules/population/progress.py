"""Bounded, worker-only staging progress measurements for Datahugger-NG population."""

import logging
import threading
from pathlib import Path
from typing import TYPE_CHECKING, Callable

from modules.population.downloader import sanitize_download_exception
from modules.population.receipt import staging_dir, write_receipt

if TYPE_CHECKING:
    from datahugger import Dataset

logger = logging.getLogger(__name__)

PROGRESS_SAMPLE_INTERVAL_SECONDS = 2.0
_SAMPLER_JOIN_TIMEOUT = 10


def crawl_file_totals(dataset: "Dataset") -> tuple[int, int | None]:
    """
    Count selected downloadable entries from the pre-download crawl.

    The byte total is published only when every selected entry has a known size;
    otherwise it remains unknown rather than a misleading partial sum.

    Native crawl failures are translated at this binding boundary, like download failures.
    """
    files_total = 0
    bytes_total = 0
    all_known = True
    try:
        entries = iter(dataset.crawl_file())
        for entry in entries:
            if not entry.downloadable:
                continue
            files_total += 1
            if entry.size is None:
                all_known = False
            else:
                bytes_total += int(entry.size)
    except Exception as exc:
        raise sanitize_download_exception(exc) from exc
    return files_total, (bytes_total if files_total and all_known else None)


def scan_staging(root: Path) -> tuple[int, int]:
    """
    Count regular files and observed bytes in staging.

    This is a “files present” measurement: it never follows symlinks and never
    claims that a file has finished downloading or passed validation.
    """
    files_present = 0
    bytes_present = 0
    if not root.is_dir():
        return files_present, bytes_present

    stack = [root]
    while stack:
        try:
            entries = list(stack.pop().iterdir())
        except OSError:
            continue
        for entry in entries:
            try:
                if entry.is_symlink():
                    continue
                if entry.is_dir(follow_symlinks=False):
                    stack.append(entry)
                elif entry.is_file(follow_symlinks=False):
                    files_present += 1
                    bytes_present += entry.stat(follow_symlinks=False).st_size
            except OSError:
                continue
    return files_present, bytes_present


class ProgressSampler:
    """Periodically records staging progress while the blocking native download runs."""

    def __init__(
        self,
        operation_id: str,
        *,
        phase: str,
        files_total: int | None = None,
        bytes_total: int | None = None,
        interval_seconds: float = PROGRESS_SAMPLE_INTERVAL_SECONDS,
        writer: Callable[..., None] = write_receipt,
    ) -> None:
        """Bind the sampling parameters; the receipt writer is injectable for tests."""
        self._operation_id = operation_id
        self._phase = phase
        self._files_total = files_total
        self._bytes_total = bytes_total
        self._interval = interval_seconds
        self._writer = writer
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._terminal = False
        self._last: tuple[int, int] = (0, 0)
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        """Start the daemon sampler (the download owns the main thread)."""
        self._thread = threading.Thread(target=self._run, name="population-progress", daemon=True)
        self._thread.start()

    def stop_and_finish(self) -> tuple[int, int]:
        """Stop the sampler and close the write barrier before a terminal receipt."""
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=_SAMPLER_JOIN_TIMEOUT)
            if self._thread.is_alive():
                logger.warning("Population %s progress sampler did not stop in time", self._operation_id)
        with self._lock:
            self._terminal = True
            return self._last

    def _run(self) -> None:
        while not self._stop.wait(self._interval):
            try:
                self._last = scan_staging(staging_dir(self._operation_id))
            except Exception:
                logger.exception("Population %s progress scan failed", self._operation_id)
                continue
            files_present, bytes_present = self._last
            with self._lock:
                if self._terminal:
                    return
                try:
                    self._writer(
                        self._operation_id,
                        "running",
                        phase=self._phase,
                        files_present=files_present,
                        files_total=self._files_total,
                        bytes_present=bytes_present,
                        bytes_total=self._bytes_total,
                    )
                except Exception:
                    logger.exception("Population %s progress receipt failed", self._operation_id)
