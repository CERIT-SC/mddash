import logging
import os
import time

import k8s_client
import metrics
from enums import JobStatus
from extensions import db
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
            except k8s_client.K8S_ERRORS as e:
                db.session.rollback()
                logger.warning("Could not poll job %s: %s", job.job_name, k8s_client.describe_error(e))
            except Exception as e:
                db.session.rollback()
                logger.exception("Error polling job %s: %s", job.job_name, e)


def run(app: Flask, interval: int) -> None:
    """Poll job statuses in a loop, sleeping ``interval`` seconds between runs."""
    logger.info("Starting poller loop every %d seconds", interval)
    while True:
        poll_once(app)
        time.sleep(interval)


if __name__ == "__main__":
    from app import app as flask_app

    if metrics_port := os.getenv("METRICS_PORT"):
        metrics.serve(flask_app, int(metrics_port))
    run(flask_app, int(os.getenv("POLL_INTERVAL_SECONDS", "900")))
