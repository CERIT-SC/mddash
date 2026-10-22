"""Durable archive Kubernetes Job submission (deterministic names, S3 creds via env)."""

from __future__ import annotations

import logging
import secrets
from typing import TYPE_CHECKING, Any

from core.cache import archive_status_cache
from core.config import (
    ARCHIVE_WORKER_IMAGE,
    S3_ACCESS_KEY,
    S3_BUCKET,
    S3_ENDPOINT,
    S3_SECRET_KEY,
)
from core.worker_jobs import (
    DELETION_TIMEOUT,
    EXPERIMENT_LABEL,
    SubmissionError,
    delete_worker_job,
    dns1123_name,
    worker_job_manifest,
)

from modules.archive.status import ArchiveDirection, create_queued_status, delete_status, read_status, write_status

if TYPE_CHECKING:
    from pathlib import Path

    from clients.k8s import K8sClient

logger = logging.getLogger(__name__)

ARCHIVE_APP_LABEL = "archive-worker"
ADMISSION_TIMEOUT = 30

_TRACKED_DIRECTIONS = (ArchiveDirection.ARCHIVE.value, ArchiveDirection.RESTORE.value)
_ALL_MODES = (*_TRACKED_DIRECTIONS, "purge")


def job_name(direction: str, experiment_id: str) -> str:
    return dns1123_name(direction, experiment_id, fallback_prefix=direction)


def _job_manifest(name: str, direction: str, experiment_id: str, attempt_id: str) -> dict[str, Any]:
    return worker_job_manifest(
        name=name,
        app=ARCHIVE_APP_LABEL,
        experiment_id=experiment_id,
        container="worker",
        image=ARCHIVE_WORKER_IMAGE,
        args=[direction, "--experiment-id", experiment_id, "--attempt-id", attempt_id],
        env=[
            {"name": "S3_BUCKET", "value": S3_BUCKET},
            {"name": "S3_ENDPOINT", "value": S3_ENDPOINT},
            {"name": "S3_ACCESS_KEY", "value": S3_ACCESS_KEY},
            {"name": "S3_SECRET_KEY", "value": S3_SECRET_KEY},
        ],
    )


async def _submit(k8s: K8sClient, direction: str, experiment_id: str, data_dir: Path) -> str:
    name = job_name(direction, experiment_id)

    if not ARCHIVE_WORKER_IMAGE:
        raise SubmissionError("ARCHIVE_WORKER_IMAGE is not set. Redeploy the Helm chart and restart the server.")

    try:
        if await is_job_active(k8s, direction, experiment_id):
            logger.info("Job %s already active for experiment %s", name, experiment_id)
            archive_status_cache[direction, experiment_id] = True
            status = read_status(experiment_id, data_dir)
            return status.attempt_id if status else ""

        await delete_jobs(k8s, experiment_id)
        # Foreground deletion races a same-name recreate ("object is being deleted"); wait it out.
        if not await k8s.wait_for_resource_absence("job", name, max_wait=DELETION_TIMEOUT):
            raise SubmissionError(f"Previous archive Job {name} is still terminating; retry shortly.")

        attempt_id = secrets.token_hex(8)
        # Restore gets no queued doc: writing one would re-create the dir the worker
        # refuses to overwrite. Restore in-flight is reconstituted from the live Job.
        if direction == ArchiveDirection.ARCHIVE.value:
            write_status(create_queued_status(attempt_id, direction), experiment_id, data_dir)
    except SubmissionError:
        raise
    except Exception as e:
        logger.error("Failed to prepare Job %s: %s", name, e)
        raise SubmissionError(f"Failed to prepare archive Job: {e}") from e

    try:
        await k8s.create_job_raw(_job_manifest(name, direction, experiment_id, attempt_id))

        if not await k8s.wait_for_pod_admission(f"{EXPERIMENT_LABEL}={experiment_id}", max_wait=ADMISSION_TIMEOUT):
            logger.error("Pod admission timeout for Job %s", name)
            await delete_jobs(k8s, experiment_id)
            _cleanup_own_status(direction, experiment_id, data_dir)
            raise SubmissionError(f"Archive pod not admitted within {ADMISSION_TIMEOUT}s")

        logger.info("Job %s admitted for experiment %s (attempt %s)", name, experiment_id, attempt_id)
        # Write through the 1s liveness cache: the first poll after the 202 sees this Job live.
        archive_status_cache[direction, experiment_id] = True
        return attempt_id
    except SubmissionError:
        raise
    except Exception as e:
        logger.error("Failed to submit Job %s: %s", name, e)
        await delete_jobs(k8s, experiment_id)
        _cleanup_own_status(direction, experiment_id, data_dir)
        raise SubmissionError(f"Failed to submit archive Job: {e}") from e


def _cleanup_own_status(direction: str, experiment_id: str, data_dir: Path) -> None:
    """
    Only archive's own queued doc is this call's to roll back.

    A restore doc is the previous attempt's retry sentinel and must survive.
    """
    if direction == ArchiveDirection.ARCHIVE.value:
        delete_status(experiment_id, data_dir)


async def submit_job(k8s: K8sClient, direction: str, experiment_id: str, data_dir: Path) -> str:
    """
    Submit an archive or restore Job (the live one when already running).

    Raises:
        ValueError: If the direction is neither archive nor restore.
    """
    if direction not in _TRACKED_DIRECTIONS:
        raise ValueError(f"Unknown tracked archive direction: {direction}")
    return await _submit(k8s, direction, experiment_id, data_dir)


async def submit_purge_job(k8s: K8sClient, experiment_id: str) -> None:
    """Best-effort deletion of _archives/<id> after the DB row is gone: no status doc, no admission wait."""
    if not ARCHIVE_WORKER_IMAGE:
        logger.error("ARCHIVE_WORKER_IMAGE not set; skipping S3 archive purge for %s", experiment_id)
        return
    name = job_name("purge", experiment_id)
    try:
        await delete_worker_job(k8s, name)
        await k8s.create_job_raw(_job_manifest(name, "purge", experiment_id, secrets.token_hex(8)))
        logger.info("Purge Job %s submitted for experiment %s", name, experiment_id)
    except Exception:
        # Residual _archives objects cost storage, not correctness.
        logger.exception("Failed to submit purge Job for experiment %s", experiment_id)


async def is_job_active(k8s: K8sClient, direction: str, experiment_id: str) -> bool:
    """
    Live until a Complete/Failed condition lands; Pending pods (scheduling, image pull) count.

    Counting the pre-start window as dead would flash failed states and stop UI polling.
    """
    job_obj = await k8s.read_job(job_name(direction, experiment_id))
    if job_obj is None:
        return False
    status = getattr(job_obj, "status", None)
    conditions = getattr(status, "conditions", None) if status else None
    for condition in conditions or []:
        if getattr(condition, "type", None) in {"Complete", "Failed"} and getattr(condition, "status", None) == "True":
            return False
    return True


async def delete_jobs(k8s: K8sClient, experiment_id: str) -> None:
    """Delete every archive/restore/purge Job of the experiment."""
    for direction in _ALL_MODES:
        await k8s.delete_job_foreground(job_name(direction, experiment_id))
