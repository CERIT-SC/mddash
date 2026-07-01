import logging
import os
import time

from enums import JobStatus
from flask import Flask
from models import MdrunJob

logger = logging.getLogger(__name__)


def poll_once(app: Flask) -> None:
    """Refresh active job statuses once."""
    with app.app_context():
        active_statuses = [JobStatus.PENDING, JobStatus.UNKNOWN, JobStatus.RUNNING]
        jobs: list[MdrunJob] = MdrunJob.query.filter(MdrunJob.last_status.in_(active_statuses)).all()

        logger.info("Polling %d active jobs", len(jobs))

        for job in jobs:
            try:
                _ = job.status
            except Exception as e:
                logger.exception("Error polling job %s: %s", job.job_name, e)


def run(app: Flask, interval: int) -> None:
    """Poll job statuses in a loop, sleeping ``interval`` seconds between runs."""
    logger.info("Starting poller loop every %d seconds", interval)
    while True:
        poll_once(app)
        time.sleep(interval)


if __name__ == "__main__":
    from app import app as flask_app

    run(flask_app, int(os.getenv("POLL_INTERVAL_SECONDS", "900")))
