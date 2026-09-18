"""Durable archive Kubernetes Job submission (deterministic names, S3 creds via env)."""

from __future__ import annotations

import logging
import secrets
from typing import TYPE_CHECKING, Any

from cache import archive_status_cache
from clients import k8s
from config import (
    ARCHIVE_WORKER_IMAGE,
    IMAGE_PULL_POLICY,
    NAMESPACE,
    PVC_NAME,
    S3_ACCESS_KEY,
    S3_BUCKET,
    S3_ENDPOINT,
    S3_SECRET_KEY,
)

from archive.status import ArchiveDirection, create_queued_status, delete_status, read_status, write_status

if TYPE_CHECKING:
    from pathlib import Path

logger = logging.getLogger(__name__)

ARCHIVE_APP_LABEL = "archive-worker"
PRESERVE_LABEL = "mddash.io/preserve-on-stop"
EXPERIMENT_LABEL = "mddash.io/experiment"

ACTIVE_DEADLINE_SECONDS = 86400
JOB_TTL_SECONDS = 300
ADMISSION_TIMEOUT = 30
JOB_DELETION_TIMEOUT = 30
JOB_RESOURCES = {
    "requests": {"cpu": "100m", "memory": "128Mi"},
    "limits": {"cpu": "500m", "memory": "512Mi"},
}

_TRACKED_DIRECTIONS = (ArchiveDirection.ARCHIVE.value, ArchiveDirection.RESTORE.value)
_ALL_MODES = (*_TRACKED_DIRECTIONS, "purge")


class SubmissionError(Exception):
    """Raised when archive Job submission fails."""


def job_name(direction: str, experiment_id: str) -> str:
    # Experiment IDs are 5 chars, so plain names stay under the 63-char DNS-1123 limit.
    return f"{direction}-{experiment_id}"


def _job_manifest(name: str, direction: str, experiment_id: str, attempt_id: str) -> dict[str, Any]:
    labels = {"app": ARCHIVE_APP_LABEL, EXPERIMENT_LABEL: experiment_id, PRESERVE_LABEL: "true"}
    return {
        "apiVersion": "batch/v1",
        "kind": "Job",
        "metadata": {"name": name, "namespace": NAMESPACE, "labels": labels},
        "spec": {
            "backoffLimit": 0,
            "activeDeadlineSeconds": ACTIVE_DEADLINE_SECONDS,
            "ttlSecondsAfterFinished": JOB_TTL_SECONDS,
            "template": {
                "metadata": {"labels": labels},
                "spec": {
                    "restartPolicy": "Never",
                    "automountServiceAccountToken": False,
                    "securityContext": {
                        "fsGroup": 1000,
                        "fsGroupChangePolicy": "OnRootMismatch",
                        "runAsNonRoot": True,
                        "seccompProfile": {"type": "RuntimeDefault"},
                    },
                    "containers": [
                        {
                            "securityContext": {
                                "runAsUser": 1000,
                                "runAsGroup": 1000,
                                "runAsNonRoot": True,
                                "allowPrivilegeEscalation": False,
                                "capabilities": {"drop": ["ALL"]},
                                "seccompProfile": {"type": "RuntimeDefault"},
                            },
                            "name": "worker",
                            "image": ARCHIVE_WORKER_IMAGE,
                            "imagePullPolicy": IMAGE_PULL_POLICY,
                            "resources": JOB_RESOURCES,
                            "args": [direction, "--experiment-id", experiment_id, "--attempt-id", attempt_id],
                            "env": [
                                {"name": "S3_BUCKET", "value": S3_BUCKET},
                                {"name": "S3_ENDPOINT", "value": S3_ENDPOINT},
                                {"name": "S3_ACCESS_KEY", "value": S3_ACCESS_KEY},
                                {"name": "S3_SECRET_KEY", "value": S3_SECRET_KEY},
                            ],
                            "volumeMounts": [{"mountPath": "/mddash", "name": "shared-data"}],
                        }
                    ],
                    "volumes": [{"name": "shared-data", "persistentVolumeClaim": {"claimName": PVC_NAME}}],
                },
            },
        },
    }


def _submit(direction: str, experiment_id: str, data_dir: Path) -> str:
    name = job_name(direction, experiment_id)

    if not ARCHIVE_WORKER_IMAGE:
        raise SubmissionError("ARCHIVE_WORKER_IMAGE is not set. Redeploy the Helm chart and restart the server.")

    if is_job_active(direction, experiment_id):
        logger.info("Job %s already active for experiment %s", name, experiment_id)
        archive_status_cache[direction, experiment_id] = True
        status = read_status(experiment_id, data_dir)
        return status.attempt_id if status else ""

    delete_jobs(experiment_id)
    # A foreground deletion returns before the object is actually gone; recreating
    # under the same deterministic name right away races termination (the API
    # server rejects the create with "object is being deleted"). Mirror the upload
    # flow and wait for the old Job to disappear first.
    if not k8s.wait_for_resource_absence("job", name, timeout=JOB_DELETION_TIMEOUT):
        raise SubmissionError(f"Previous archive Job {name} is still terminating; retry shortly.")

    attempt_id = secrets.token_hex(8)
    # The queued doc lives inside the experiment dir: archive's dir exists, but writing
    # one for restore would re-create the dir the worker must (a) copy into and
    # (b) refuse to overwrite. Restore in-flight is reconstituted from the live Job.
    if direction == ArchiveDirection.ARCHIVE.value:
        write_status(create_queued_status(attempt_id, direction), experiment_id, data_dir)

    try:
        k8s.create_job_raw(_job_manifest(name, direction, experiment_id, attempt_id))

        if not k8s.wait_for_pod_admission(f"{EXPERIMENT_LABEL}={experiment_id}", timeout=ADMISSION_TIMEOUT):
            logger.error("Pod admission timeout for Job %s", name)
            delete_jobs(experiment_id)
            _cleanup_own_status(direction, experiment_id, data_dir)
            raise SubmissionError(f"Archive pod not admitted within {ADMISSION_TIMEOUT}s")

        logger.info("Job %s admitted for experiment %s (attempt %s)", name, experiment_id, attempt_id)
        # Write through the short liveness cache: the first poll after the 202
        # must see this Job live, not the terminal one it replaced.
        archive_status_cache[direction, experiment_id] = True
        return attempt_id
    except SubmissionError:
        raise
    except Exception as e:
        logger.error("Failed to submit Job %s: %s", name, e)
        delete_jobs(experiment_id)
        _cleanup_own_status(direction, experiment_id, data_dir)
        raise SubmissionError(f"Failed to submit archive Job: {e}") from e


def _cleanup_own_status(direction: str, experiment_id: str, data_dir: Path) -> None:
    """
    Roll back a failed submission: only archive has a queued doc written by this call.

    Restore never writes one; the doc in its leftover dir is the previous attempt's
    retry sentinel and must survive submission failures, or a partially-restored dir
    loses the marker that makes it re-submittable.
    """
    if direction == ArchiveDirection.ARCHIVE.value:
        delete_status(experiment_id, data_dir)


def submit_job(direction: str, experiment_id: str, data_dir: Path) -> str:
    if direction not in _TRACKED_DIRECTIONS:
        raise ValueError(f"Unknown tracked archive direction: {direction}")
    return _submit(direction, experiment_id, data_dir)


def submit_purge_job(experiment_id: str) -> None:
    """Best-effort deletion of _archives/<id> after the DB row is gone: no status doc, no admission wait."""
    if not ARCHIVE_WORKER_IMAGE:
        logger.error("ARCHIVE_WORKER_IMAGE not set; skipping S3 archive purge for %s", experiment_id)
        return
    name = job_name("purge", experiment_id)
    try:
        k8s.delete_job_foreground(name)
        k8s.wait_for_resource_absence("job", name, timeout=JOB_DELETION_TIMEOUT)
        k8s.create_job_raw(_job_manifest(name, "purge", experiment_id, secrets.token_hex(8)))
        logger.info("Purge Job %s submitted for experiment %s", name, experiment_id)
    except Exception:
        # Residual _archives objects cost storage, not correctness.
        logger.exception("Failed to submit purge Job for experiment %s", experiment_id)


def is_job_active(direction: str, experiment_id: str) -> bool:
    """
    Live until a terminal condition lands; a Pending pod (scheduling, image pull) counts.

    Counting the pre-start window as dead would flash failed states right after
    submission and stop the UI polling that reports progress.
    """
    job_obj = k8s.read_job(job_name(direction, experiment_id))
    if job_obj is None:
        return False
    status = getattr(job_obj, "status", None)
    conditions = getattr(status, "conditions", None) if status else None
    for condition in conditions or []:
        if getattr(condition, "type", None) in {"Complete", "Failed"} and getattr(condition, "status", None) == "True":
            return False
    return True


def delete_jobs(experiment_id: str) -> None:
    for direction in _ALL_MODES:
        k8s.delete_job_foreground(job_name(direction, experiment_id))
