"""
Durable worker Jobs (MDRepo uploader, archive worker) and the status docs they share with the API.

The Job outlives the request that submits it; progress travels through a JSON status
doc on the shared PVC, written atomically so a reader never sees a torn file.
"""

import contextlib
import hashlib
import json
import logging
import os
import re
import tempfile
from pathlib import Path
from typing import TYPE_CHECKING, Any

from core.config import IMAGE_PULL_POLICY, NAMESPACE, PVC_NAME

if TYPE_CHECKING:
    from clients.k8s import K8sClient

logger = logging.getLogger(__name__)

PRESERVE_LABEL = "mddash.io/preserve-on-stop"
EXPERIMENT_LABEL = "mddash.io/experiment"

ACTIVE_DEADLINE_SECONDS = 86400  # 24 hours
TTL_SECONDS = 300  # 5 minutes after completion
DELETION_TIMEOUT = 30  # seconds
RESOURCES = {
    "requests": {"cpu": "100m", "memory": "128Mi"},
    "limits": {"cpu": "500m", "memory": "256Mi"},
}
_SECURITY_CONTEXT = {
    "runAsUser": 1000,
    "runAsGroup": 1000,
    "runAsNonRoot": True,
    "allowPrivilegeEscalation": False,
    "capabilities": {"drop": ["ALL"]},
    "seccompProfile": {"type": "RuntimeDefault"},
}


class SubmissionError(Exception):
    """Raised when a worker Job cannot be submitted or admitted."""


def dns1123_name(*parts: str, fallback_prefix: str = "mdrepo-upload") -> str:
    """Append a hash suffix if truncation is needed to stay under the 63-char limit."""
    raw = "-".join(p for p in parts if p)
    safe = re.sub(r"[^a-z0-9-]+", "-", raw.lower()).strip("-")
    safe = re.sub(r"-+", "-", safe)
    max_base = 50
    if len(safe) > max_base:
        digest = hashlib.sha256(raw.encode()).hexdigest()[:8]
        safe = safe[:max_base].rstrip("-") + "-" + digest
    if not safe or not re.match(r"^[a-z0-9]([-a-z0-9]*[a-z0-9])?$", safe):
        safe = fallback_prefix + "-" + hashlib.sha256(raw.encode()).hexdigest()[:8]
    return safe


def worker_job_manifest(
    *,
    name: str,
    app: str,
    experiment_id: str,
    container: str,
    image: str,
    args: list[str],
    env: list[dict[str, Any]],
    command: list[str] | None = None,
) -> dict[str, Any]:
    """Job manifest of a worker on the shared PVC: no retries, no service account token, e-INFRA security context."""
    labels = {"app": app, EXPERIMENT_LABEL: experiment_id, PRESERVE_LABEL: "true"}
    spec: dict[str, Any] = {
        "securityContext": _SECURITY_CONTEXT,
        "name": container,
        "image": image,
        "imagePullPolicy": IMAGE_PULL_POLICY,
        "resources": RESOURCES,
        **({"command": command} if command else {}),
        "args": args,
        "env": env,
        "volumeMounts": [{"mountPath": "/mddash", "name": "shared-data"}],
    }
    return {
        "apiVersion": "batch/v1",
        "kind": "Job",
        "metadata": {"name": name, "namespace": NAMESPACE, "labels": labels},
        "spec": {
            "backoffLimit": 0,
            "activeDeadlineSeconds": ACTIVE_DEADLINE_SECONDS,
            "ttlSecondsAfterFinished": TTL_SECONDS,
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
                    "containers": [spec],
                    "volumes": [{"name": "shared-data", "persistentVolumeClaim": {"claimName": PVC_NAME}}],
                },
            },
        },
    }


async def delete_worker_job(k8s: "K8sClient", name: str) -> bool:
    """Foreground-delete a worker Job; True once it is gone (a same-name recreate would race the deletion)."""
    await k8s.delete_job_foreground(name)
    return await k8s.wait_for_resource_absence("job", name, max_wait=DELETION_TIMEOUT)


def read_status_doc(path: Path) -> dict | None:
    """Read the status doc's JSON (None when it is missing or corrupt)."""
    try:
        content = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return None
    except OSError:
        logger.exception("Failed to read status file %s", path)
        return None
    try:
        return json.loads(content)
    except json.JSONDecodeError:
        logger.error("Corrupt status file %s", path)
        return None


def write_status_doc(path: Path, data: dict) -> None:
    """Write the status doc atomically (temp file, fsync, rename)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(dir=str(path.parent), prefix=path.name + ".", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(json.dumps(data, indent=2))
            f.flush()
            os.fsync(f.fileno())
        Path(tmp_name).replace(path)
    except OSError:
        logger.exception("Failed to write status file %s", path)
        with contextlib.suppress(OSError):
            Path(tmp_name).unlink()
        raise
