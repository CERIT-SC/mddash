"""
One-shot Datahugger-NG population worker (runs in the Dashboard API image).

The worker writes only the staged dataset and its atomic receipt; it never
opens the database and never creates the Experiment. Native exception details
stay in the worker logs; the receipt carries a stable user-safe message.

Run as: python -m modules.population.worker --operation-id ID --experiment-id ID --repo-url URL
"""

import argparse
import logging
from typing import TYPE_CHECKING

from modules.population.downloader import PopulationDownloadError, download_resolved, resolve_dataset
from modules.population.progress import PROGRESS_SAMPLE_INTERVAL_SECONDS, ProgressSampler, crawl_file_totals
from modules.population.receipt import staging_dir, write_receipt

if TYPE_CHECKING:
    from collections.abc import Sequence

logger = logging.getLogger(__name__)

RECEIPT_ERROR_DOWNLOAD_FAILED = "The repository download failed. Contact support if the failure persists."


def _safe_error(exc: Exception) -> str:
    """Keep the curated binding message; every other native detail stays private to the log."""
    return str(exc) if isinstance(exc, PopulationDownloadError) else RECEIPT_ERROR_DOWNLOAD_FAILED


def run_download(repo_url: str, operation_id: str) -> None:
    """Download the full repository into staging and write a terminal receipt."""
    dst = staging_dir(operation_id)
    dst.mkdir(parents=True, exist_ok=True)

    write_receipt(operation_id, "running", phase="starting")

    try:
        dataset = resolve_dataset(repo_url)
    except Exception as exc:
        logger.exception("Population %s resolution failed for %s", operation_id, repo_url)
        write_receipt(operation_id, "failed", _safe_error(exc), phase="starting")
        raise

    write_receipt(operation_id, "running", phase="crawling")
    try:
        files_total, bytes_total = crawl_file_totals(dataset)
    except Exception as exc:
        logger.exception("Population %s crawl failed for %s", operation_id, repo_url)
        write_receipt(operation_id, "failed", _safe_error(exc), phase="crawling")
        raise

    write_receipt(
        operation_id,
        "running",
        phase="downloading",
        files_total=files_total,
        bytes_total=bytes_total,
    )
    sampler = ProgressSampler(
        operation_id,
        phase="downloading",
        files_total=files_total,
        bytes_total=bytes_total,
        interval_seconds=PROGRESS_SAMPLE_INTERVAL_SECONDS,
    )
    sampler.start()
    try:
        downloaded = download_resolved(dataset, dst)
        logger.info("Population %s downloaded %s files into %s", operation_id, downloaded, dst)
    except Exception as exc:
        files_present, bytes_present = sampler.stop_and_finish()
        logger.exception("Population %s download failed for %s", operation_id, repo_url)
        write_receipt(
            operation_id,
            "failed",
            _safe_error(exc),
            phase="downloading",
            files_present=files_present,
            files_total=files_total,
            bytes_present=bytes_present,
            bytes_total=bytes_total,
        )
        raise

    files_present, bytes_present = sampler.stop_and_finish()
    write_receipt(
        operation_id,
        "succeeded",
        phase="finalizing",
        files_present=files_present,
        files_total=files_total,
        bytes_present=bytes_present,
        bytes_total=bytes_total,
    )


def main(argv: "Sequence[str] | None" = None) -> int:
    """Parse worker arguments, announce running state, and perform the download."""
    parser = argparse.ArgumentParser(description="Datahugger-NG population worker")
    parser.add_argument("--operation-id", required=True)
    parser.add_argument("--experiment-id", required=True)
    parser.add_argument("--repo-url", required=True)
    args = parser.parse_args(argv)

    logger.info("Population worker started (operation=%s experiment=%s)", args.operation_id, args.experiment_id)
    try:
        run_download(args.repo_url, args.operation_id)
    except Exception:
        # The terminal receipt already carries the stable, user-safe cause; the
        # raw traceback remains here, server-side only.
        return 1
    return 0


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    raise SystemExit(main())
