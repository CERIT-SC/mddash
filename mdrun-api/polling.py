import logging
import os
import threading
import time

from enums import JobStatus
from flask import Flask
from models import MdrunJob

logger = logging.getLogger(__name__)

# Poll every 15 minutes
POLL_INTERVAL_SECONDS = 15 * 60


def _polling_worker(app: Flask) -> None:
    """Background worker that polls job statuses periodically."""
    logger.info(f"Starting job status polling worker (interval: {POLL_INTERVAL_SECONDS}s)")

    while True:
        try:
            with app.app_context():
                # Query all active jobs
                active_statuses = [JobStatus.PENDING, JobStatus.UNKNOWN, JobStatus.RUNNING]
                jobs: list[MdrunJob] = MdrunJob.query.filter(MdrunJob.last_status.in_(active_statuses)).all()

                logger.info(f"Polling {len(jobs)} active jobs")

                for job in jobs:
                    try:
                        # Access the status property to trigger the update
                        _ = job.status
                    except Exception as e:
                        logger.exception(f"Error polling job {job.job_name}: {e}")

        except Exception as e:
            logger.exception(f"Error in polling worker: {e}")

        # Wait for the next polling interval
        time.sleep(POLL_INTERVAL_SECONDS)


def start_polling(app: Flask) -> None:
    """
    Start the background polling thread.

    Only runs in the first uWSGI worker to avoid duplicate polling.
    """
    # In uWSGI, only start polling in worker 1
    worker_id = os.environ.get("UWSGI_WORKER_ID", "1")

    if worker_id != "1":
        logger.info(f"Skipping polling worker in uWSGI worker {worker_id}")
        return

    logger.info("Starting polling worker in uWSGI worker 1")
    thread = threading.Thread(target=_polling_worker, args=(app,), daemon=True, name="JobStatusPoller")
    thread.start()
    logger.info("Job status polling thread started")
