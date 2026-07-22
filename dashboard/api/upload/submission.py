"""
Durable MDRepo upload Kubernetes Job submission.

The Job name is deterministic by experiment ID, so a repeated publish request
returns the existing Job instead of creating a duplicate.
"""

from __future__ import annotations

import hashlib
import logging
import re
import secrets
from typing import TYPE_CHECKING, Any

from clients import k8s
from config import IMAGE_PULL_POLICY, MDREPO_UPLOADER_IMAGE, NAMESPACE, PVC_NAME

from upload.status import create_queued_status, read_status, write_status

if TYPE_CHECKING:
    from pathlib import Path

logger = logging.getLogger(__name__)

UPLOAD_APP_LABEL = "mdrepo-uploader"
PRESERVE_LABEL = "mddash.io/preserve-on-stop"
EXPERIMENT_LABEL = "mddash.io/experiment"

# Not per-deployment configurable.
UPLOAD_ACTIVE_DEADLINE_SECONDS = 86400  # 24 hours
UPLOAD_TTL_SECONDS = 300  # 5 minutes after completion
UPLOAD_ADMISSION_TIMEOUT = 30  # seconds
UPLOAD_RESOURCES = {
    "requests": {"cpu": "100m", "memory": "128Mi"},
    "limits": {"cpu": "500m", "memory": "256Mi"},
}


def _dns1123_name(*parts: str) -> str:
    """
    Append a hash suffix if truncation is needed to stay under the 63-char limit.

    Returns:
        DNS-1123 compliant name.
    """
    raw = "-".join(p for p in parts if p)
    safe = re.sub(r"[^a-z0-9-]+", "-", raw.lower()).strip("-")
    safe = re.sub(r"-+", "-", safe)
    max_base = 50
    if len(safe) > max_base:
        digest = hashlib.sha256(raw.encode()).hexdigest()[:8]
        safe = safe[:max_base].rstrip("-") + "-" + digest
    if not safe or not re.match(r"^[a-z0-9]([-a-z0-9]*[a-z0-9])?$", safe):
        safe = "mdrepo-upload-" + hashlib.sha256(raw.encode()).hexdigest()[:8]
    return safe


def job_name(experiment_id: str) -> str:
    """
    Deterministic name for an experiment's upload Job.

    Returns:
        DNS-1123 compliant name.
    """
    return _dns1123_name("mdrepo-upload", experiment_id)


def secret_name(experiment_id: str) -> str:
    """
    Deterministic name for an experiment's upload Secret.

    Returns:
        DNS-1123 compliant name.
    """
    return _dns1123_name("mdrepo-upload-cred", experiment_id)


def build_credential_secret_data(
    access_token: str,
    refresh_token: str,
    token_expires_at: float,
    client_id: str,
    client_secret: str,
    api_url: str,
    record_name: str,
    token_url: str,
) -> dict[str, str]:
    """
    Build credential string data for the upload Secret.

    Only OAuth credentials and MDRepo endpoint info. The worker receives
    experiment_id, mdrepo_id, and attempt_id as CLI arguments, so they must
    not appear in the Secret (visible in the API object).

    Returns:
        Env-var key-value pairs for the Secret.
    """
    return {
        "MDREPO_ACCESS_TOKEN": access_token,
        "MDREPO_REFRESH_TOKEN": refresh_token,
        "MDREPO_TOKEN_EXPIRES_AT": str(token_expires_at),
        "MDREPO_CLIENT_ID": client_id,
        "MDREPO_CLIENT_SECRET": client_secret,
        "MDREPO_API_URL": api_url,
        "MDREPO_RECORD_NAME": record_name,
        "MDREPO_TOKEN_URL": token_url,
    }


class SubmissionError(Exception):
    """Raised when upload Job submission fails."""


def submit_upload_job(
    experiment_id: str,
    mdrepo_id: str,
    credential_data: dict[str, str],
    data_dir: Path,
) -> str:
    """
    Submit a durable MDRepo upload as a Kubernetes Job.

    If the Job already exists and is active, returns the existing attempt ID
    without creating a new one. Otherwise: generates a fresh attempt ID, writes
    queued status to the PVC, creates the Secret and Job, and waits for pod
    admission. On failure, cleans up all created resources.

    Returns:
        The attempt ID.

    Raises:
        SubmissionError: If submission fails before pod admission.
    """
    j_name = job_name(experiment_id)
    s_name = secret_name(experiment_id)

    existing_status = _read_attempt_id(experiment_id, data_dir)
    if is_upload_active(experiment_id):
        logger.info("Upload Job %s already active for experiment %s", j_name, experiment_id)
        return existing_status or ""

    # Clean up any terminal Job from a previous attempt before retrying.
    delete_upload_resources(experiment_id)

    attempt_id = secrets.token_hex(8)
    write_status(create_queued_status(attempt_id), experiment_id, data_dir)

    labels = {
        "app": UPLOAD_APP_LABEL,
        EXPERIMENT_LABEL: experiment_id,
        PRESERVE_LABEL: "true",
    }

    container = {
        "securityContext": {
            "runAsUser": 1000,
            "runAsGroup": 1000,
            "runAsNonRoot": True,
            "allowPrivilegeEscalation": False,
            "capabilities": {"drop": ["ALL"]},
            "seccompProfile": {"type": "RuntimeDefault"},
        },
        "name": "uploader",
        "image": MDREPO_UPLOADER_IMAGE,
        "imagePullPolicy": IMAGE_PULL_POLICY,
        "resources": UPLOAD_RESOURCES,
        "command": ["python", "/worker.py"],
        "args": ["--experiment-id", experiment_id, "--mdrepo-id", mdrepo_id, "--attempt-id", attempt_id],
        "volumeMounts": [{"mountPath": "/mddash", "name": "shared-data"}],
        "envFrom": [{"secretRef": {"name": s_name}}],
    }

    job_manifest: dict[str, Any] = {
        "apiVersion": "batch/v1",
        "kind": "Job",
        "metadata": {"name": j_name, "namespace": NAMESPACE, "labels": labels},
        "spec": {
            "backoffLimit": 0,
            "activeDeadlineSeconds": UPLOAD_ACTIVE_DEADLINE_SECONDS,
            "ttlSecondsAfterFinished": UPLOAD_TTL_SECONDS,
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
                    "containers": [container],
                    "volumes": [{"name": "shared-data", "persistentVolumeClaim": {"claimName": PVC_NAME}}],
                },
            },
        },
    }

    try:
        # Secret must exist before the pod starts (envFrom at startup).
        k8s.create_secret(s_name, credential_data)
        k8s.create_job_raw(job_manifest)

        label_selector = f"{EXPERIMENT_LABEL}={experiment_id}"
        if not k8s.wait_for_pod_admission(label_selector, timeout=UPLOAD_ADMISSION_TIMEOUT):
            logger.error("Pod admission timeout for Job %s", j_name)
            delete_upload_resources(experiment_id)
            raise SubmissionError(f"Upload pod not admitted within {UPLOAD_ADMISSION_TIMEOUT}s")

        logger.info("Upload Job %s admitted for experiment %s", j_name, experiment_id)
        return attempt_id

    except SubmissionError:
        raise
    except Exception as e:
        logger.error("Failed to submit upload Job %s: %s", j_name, e)
        delete_upload_resources(experiment_id)
        raise SubmissionError(f"Failed to submit upload Job: {e}") from e


def is_upload_active(experiment_id: str) -> bool:
    """
    Check whether the upload Job for the given experiment is still active.

    Returns:
        True if the Job exists and has an active pod.
    """
    j_name = job_name(experiment_id)
    job_obj = k8s.read_job(j_name)
    if job_obj is None:
        return False
    status = getattr(job_obj, "status", None)
    active = getattr(status, "active", 0) if status else 0
    return active > 0


def delete_upload_resources(experiment_id: str) -> None:
    """Foreground-delete the Job and explicitly delete the credential Secret."""
    j_name = job_name(experiment_id)
    s_name = secret_name(experiment_id)
    k8s.delete_job_foreground(j_name)
    k8s.delete_secret(s_name)
    k8s.wait_for_resource_absence("job", j_name, timeout=30)
    k8s.wait_for_resource_absence("secret", s_name, timeout=10)


def _read_attempt_id(experiment_id: str, data_dir: Path) -> str | None:
    """
    Attempt ID from the PVC status file, or None if no status exists.

    Returns:
        The attempt ID string, or None.
    """
    status = read_status(experiment_id, data_dir)
    return status.attempt_id if status else None
