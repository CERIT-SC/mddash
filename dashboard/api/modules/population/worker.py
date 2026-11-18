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

from modules.population.downloader import download_dataset
from modules.population.receipt import staging_dir, write_receipt

if TYPE_CHECKING:
    from collections.abc import Sequence

logger = logging.getLogger(__name__)

RECEIPT_ERROR_DOWNLOAD_FAILED = "The repository download failed."


def run_download(repo_url: str, operation_id: str) -> None:
    """Download the full repository into staging and write a terminal receipt."""
    dst = staging_dir(operation_id)
    dst.mkdir(parents=True, exist_ok=True)
    try:
        downloaded = download_dataset(repo_url, dst)
    except Exception:
        logger.exception("Population %s failed for %s", operation_id, repo_url)
        write_receipt(operation_id, "failed", RECEIPT_ERROR_DOWNLOAD_FAILED)
        return
    logger.info("Population %s downloaded %s files into %s", operation_id, downloaded, dst)
    write_receipt(operation_id, "succeeded")


def main(argv: "Sequence[str] | None" = None) -> int:
    """Parse worker arguments, announce running state, and perform the download."""
    parser = argparse.ArgumentParser(description="Datahugger-NG population worker")
    parser.add_argument("--operation-id", required=True)
    parser.add_argument("--experiment-id", required=True)
    parser.add_argument("--repo-url", required=True)
    args = parser.parse_args(argv)

    logger.info("Population worker started (operation=%s experiment=%s)", args.operation_id, args.experiment_id)
    write_receipt(args.operation_id, "running")
    run_download(args.repo_url, args.operation_id)
    return 0


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    raise SystemExit(main())
