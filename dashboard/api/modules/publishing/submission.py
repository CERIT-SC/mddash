"""Durable MDRepo upload Kubernetes Job submission (deterministic name, credentials via container env)."""

from __future__ import annotations

import logging
import secrets
from typing import TYPE_CHECKING, Any

import anyio
from core.config import MDREPO_UPLOADER_IMAGE
from core.worker_jobs import (
    EXPERIMENT_LABEL,
    SubmissionError,
    delete_worker_job,
    dns1123_name,
    worker_job_manifest,
)

from modules.publishing.status import UploadState, create_queued_status, read_status, write_status

if TYPE_CHECKING:
    from pathlib import Path

    from clients.k8s import K8sClient

logger = logging.getLogger(__name__)

UPLOAD_APP_LABEL = "mdrepo-uploader"
UPLOAD_ADMISSION_TIMEOUT = 30  # seconds


def job_name(experiment_id: str) -> str:
    """Deterministic name for an experiment's upload Job."""
    return dns1123_name("mdrepo-upload", experiment_id)


def build_credential_env(credential_data: dict[str, str]) -> list[dict[str, Any]]:
    """Convert credential data to a container env list (values embedded directly in the manifest)."""
    key_map = {
        "access_token": "MDREPO_ACCESS_TOKEN",
        "refresh_token": "MDREPO_REFRESH_TOKEN",
        "expires_at": "MDREPO_TOKEN_EXPIRES_AT",
        "client_id": "MDREPO_CLIENT_ID",
        "client_secret": "MDREPO_CLIENT_SECRET",
        "api_url": "MDREPO_API_URL",
        "record_name": "MDREPO_RECORD_NAME",
        "token_url": "MDREPO_TOKEN_URL",
    }
    return [{"name": key_map[key], "value": value} for key, value in credential_data.items()]


async def submit_upload_job(
    k8s: K8sClient,
    experiment_id: str,
    mdrepo_id: str,
    credential_data: dict[str, str],
    data_dir: Path,
) -> str:
    """Idempotently submit the upload Job (returns existing attempt if active, else creates and waits for admission)."""
    j_name = job_name(experiment_id)

    existing_status = _read_attempt_id(experiment_id, data_dir)
    if await is_upload_active(k8s, experiment_id):
        logger.info("Upload Job %s already active for experiment %s", j_name, experiment_id)
        return existing_status or ""

    # Clean up any terminal Job from a previous attempt before retrying.
    await delete_upload_resources(k8s, experiment_id)

    attempt_id = secrets.token_hex(8)
    write_status(create_queued_status(attempt_id), experiment_id, data_dir)

    if not MDREPO_UPLOADER_IMAGE:
        raise SubmissionError("MDREPO_UPLOADER_IMAGE is not set. Redeploy the Helm chart and restart the server.")

    job_manifest = worker_job_manifest(
        name=j_name,
        app=UPLOAD_APP_LABEL,
        experiment_id=experiment_id,
        container="uploader",
        image=MDREPO_UPLOADER_IMAGE,
        command=["python", "/worker.py"],
        args=["--experiment-id", experiment_id, "--mdrepo-id", mdrepo_id, "--attempt-id", attempt_id],
        env=build_credential_env(credential_data),
    )

    try:
        await k8s.create_job_raw(job_manifest)

        label_selector = f"{EXPERIMENT_LABEL}={experiment_id}"
        if not await k8s.wait_for_pod_admission(label_selector, max_wait=UPLOAD_ADMISSION_TIMEOUT):
            logger.error("Pod admission timeout for Job %s", j_name)
            await delete_upload_resources(k8s, experiment_id)
            raise SubmissionError(f"Upload pod not admitted within {UPLOAD_ADMISSION_TIMEOUT}s")

        logger.info("Upload Job %s admitted for experiment %s", j_name, experiment_id)
        return attempt_id

    except SubmissionError:
        raise
    except Exception as e:
        logger.error("Failed to submit upload Job %s: %s", j_name, e)
        await delete_upload_resources(k8s, experiment_id)
        raise SubmissionError(f"Failed to submit upload Job: {e}") from e


async def is_upload_active(k8s: K8sClient, experiment_id: str) -> bool:
    """Whether the experiment's upload Job has an active pod."""
    j_name = job_name(experiment_id)
    job_obj = await k8s.read_job(j_name)
    if job_obj is None:
        return False
    status = getattr(job_obj, "status", None)
    active = getattr(status, "active", None) if status else None
    return (active or 0) > 0


async def delete_upload_resources(k8s: K8sClient, experiment_id: str) -> None:
    """Foreground-delete the upload Job."""
    j_name = job_name(experiment_id)
    await delete_worker_job(k8s, j_name)


def _read_attempt_id(experiment_id: str, data_dir: Path) -> str | None:
    status = read_status(experiment_id, data_dir)
    return status.attempt_id if status else None


async def read_upload_state(k8s: K8sClient, experiment_id: str, data_dir: Path) -> str | None:
    """Reconcile upload state from the PVC status file and live Job (reports failed if the Job is gone)."""
    status = await anyio.to_thread.run_sync(read_status, experiment_id, data_dir)
    if status is None:
        return None

    if status.state in UploadState.terminal():
        return status.state

    if status.state in UploadState.active() and not await is_upload_active(k8s, experiment_id):
        return UploadState.FAILED.value

    return status.state
