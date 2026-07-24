"""Durable MDRepo upload Kubernetes Job submission (deterministic name, credentials via container env)."""

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
    """Append a hash suffix if truncation is needed to stay under the 63-char limit."""
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
    """Deterministic name for an experiment's upload Job."""
    return _dns1123_name("mdrepo-upload", experiment_id)


class SubmissionError(Exception):
    """Raised when upload Job submission fails."""


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


def submit_upload_job(
    experiment_id: str,
    mdrepo_id: str,
    credential_data: dict[str, str],
    data_dir: Path,
) -> str:
    """Idempotently submit the upload Job (returns existing attempt if active, else creates and waits for admission)."""
    j_name = job_name(experiment_id)

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
        "args": [
            "--experiment-id",
            experiment_id,
            "--mdrepo-id",
            mdrepo_id,
            "--attempt-id",
            attempt_id,
        ],
        "env": build_credential_env(credential_data),
        "volumeMounts": [{"mountPath": "/mddash", "name": "shared-data"}],
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
    j_name = job_name(experiment_id)
    job_obj = k8s.read_job(j_name)
    if job_obj is None:
        return False
    status = getattr(job_obj, "status", None)
    active = getattr(status, "active", 0) if status else 0
    return active > 0


def delete_upload_resources(experiment_id: str) -> None:
    """Foreground-delete the upload Job."""
    j_name = job_name(experiment_id)
    k8s.delete_job_foreground(j_name)
    k8s.wait_for_resource_absence("job", j_name, timeout=30)


def _read_attempt_id(experiment_id: str, data_dir: Path) -> str | None:
    status = read_status(experiment_id, data_dir)
    return status.attempt_id if status else None
