import logging
import os
from pathlib import Path
from urllib.parse import urlparse

from logging_utils import configure_logging

LOG_FORMAT = "[%(asctime)s] %(levelname)s\t%(name)s: %(message)s"
LOG_LEVEL = getattr(logging, os.environ.get("LOG_LEVEL", "INFO").upper(), logging.INFO)

configure_logging(LOG_FORMAT, LOG_LEVEL)

logger = logging.getLogger(__name__)


HOSTNAME = os.environ.get("HOSTNAME", "localhost")
JUPYTER_USER = os.environ.get("JUPYTERHUB_USER", "")
PREFIX = os.environ.get("JUPYTERHUB_SERVICE_PREFIX", "/").rstrip("/") + "/dash"
API_PREFIX = f"{PREFIX}/api"

DATA_DIR = Path(os.environ.get("DATA_DIR", "/mddash"))
DATA_DIR.mkdir(parents=True, exist_ok=True)

NOTEBOOK_IMAGE = os.environ.get("NOTEBOOK_IMAGE", "quay.io/jupyter/base-notebook")
NOTEBOOK_IDLE_TIMEOUT = int(os.environ.get("NOTEBOOK_IDLE_TIMEOUT", "3600"))
GPU_TYPE = os.environ.get("GPU_TYPE", "")
ANALYSIS_IMAGE = os.environ.get("ANALYSIS_IMAGE", "ghcr.io/mmb-irb/mddb_wf")

IMAGE_PULL_POLICY = os.environ.get("IMAGE_PULL_POLICY", "Always")

DEFAULT_NOTEBOOKS_REPO = os.environ.get("DEFAULT_NOTEBOOKS_REPO", "https://github.com/sb-ncbr/mddash-notebooks.git")

NAMESPACE = os.environ.get("POD_NAMESPACE", "default")

if NAMESPACE == "default":
    logger.warning("Using default namespace. Is the POD_NAMESPACE environment variable set correctly?")

HUB_NAMESPACE = os.environ.get("HUB_NAMESPACE", NAMESPACE)

MDRUN_API_URL = f"http://mdrun-api.{HUB_NAMESPACE}.svc.cluster.local/api"

TUNER_URL = f"http://tuner-api-svc.{HUB_NAMESPACE}.svc.cluster.local:8000/api"
TUNER_USER = os.environ.get("TUNER_USER", "")
TUNER_PASSWORD = os.environ.get("TUNER_PASSWORD", "")

if not all([TUNER_USER, TUNER_PASSWORD]):
    logger.warning("TUNER_USER or TUNER_PASSWORD environment variables are not set. Tuner won't work.")

PVC_NAME = os.environ.get("PVC_NAME", "")
PVC_SIZE = os.environ.get("PVC_STORAGE_SIZE", "")

if not all([PVC_NAME, PVC_SIZE]):
    logger.warning(
        "PVC_NAME or PVC_STORAGE_SIZE environment variables are not set. Persistent storage may not be configured properly."
    )

CPU_REQUEST_QUOTA = os.environ.get("NS_REQUESTS_CPU", "")
MEMORY_REQUEST_QUOTA = os.environ.get("NS_REQUESTS_MEMORY", "")
CPU_LIMIT_QUOTA = os.environ.get("NS_LIMITS_CPU", "")
MEMORY_LIMIT_QUOTA = os.environ.get("NS_LIMITS_MEMORY", "")

if not all([CPU_REQUEST_QUOTA, MEMORY_REQUEST_QUOTA, CPU_LIMIT_QUOTA, MEMORY_LIMIT_QUOTA]):
    logger.warning(
        "NS_REQUESTS_CPU, NS_REQUESTS_MEMORY, NS_LIMITS_CPU, or NS_LIMITS_MEMORY environment variables are not set. Namespace resource quota checks may not be configured properly."
    )

if "NS_MAX_NOTEBOOKS" not in os.environ:
    raise RuntimeError("NS_MAX_NOTEBOOKS environment variable is required (max concurrent notebooks per namespace).")
MAX_NOTEBOOKS = int(os.environ["NS_MAX_NOTEBOOKS"])

NOTEBOOK_RESOURCES: dict[str, dict[str, str]] = {
    "requests": {
        "cpu": os.environ.get("NOTEBOOK_CPU_REQUEST", ""),
        "memory": os.environ.get("NOTEBOOK_MEMORY_REQUEST", ""),
    },
    "limits": {"cpu": os.environ.get("NOTEBOOK_CPU_LIMIT", ""), "memory": os.environ.get("NOTEBOOK_MEMORY_LIMIT", "")},
}

ANALYSIS_RESOURCES: dict[str, dict[str, str]] = {
    "requests": {
        "cpu": os.environ.get("ANALYSIS_CPU_REQUEST", ""),
        "memory": os.environ.get("ANALYSIS_MEMORY_REQUEST", ""),
    },
    "limits": {"cpu": os.environ.get("ANALYSIS_CPU_LIMIT", ""), "memory": os.environ.get("ANALYSIS_MEMORY_LIMIT", "")},
}

if not all(v for r in (NOTEBOOK_RESOURCES, ANALYSIS_RESOURCES) for d in r.values() for v in d.values()):
    logger.warning("Pod resource env vars are not fully set. Pods may be created without resource constraints.")


S3_BUCKET = os.environ.get("S3_BUCKET", "")

if not S3_BUCKET:
    logger.warning("One or more S3 configuration environment variables are not set. S3 functionality may be limited.")

MDREPO_URL = os.environ.get("MDREPO_URL", "")
MDREPO_API_URL = f"{MDREPO_URL}/api"
MDREPO_RECORD_NAME = "datasets"
MDREPO_SCOPES = os.environ.get("MDREPO_SCOPES", "")
MDREPO_CLIENT_ID = os.environ.get("MDREPO_CLIENT_ID", "")
MDREPO_CLIENT_SECRET = os.environ.get("MDREPO_CLIENT_SECRET", "")
MDREPO_REDIRECT_URI = f"https://{HOSTNAME}/hub/user-redirect/dash/api/mdrepo/callback"
MDREPO_AUTHORIZE_URL = f"{MDREPO_URL}/oauth/authorize"
MDREPO_TOKEN_URL = f"{MDREPO_URL}/oauth/token"

if not all([MDREPO_URL, MDREPO_CLIENT_ID, MDREPO_CLIENT_SECRET, MDREPO_SCOPES]):
    logger.warning("MDRepo configuration incomplete. Publishing to MDRepo will not work properly.")

MDPOSIT_URL = os.environ.get("MDPOSIT_URL", "").rstrip("/")
MDPOSIT_HOST = urlparse(MDPOSIT_URL).netloc if MDPOSIT_URL else ""
MDPOSIT_REST_URL = f"{MDPOSIT_URL}/api/rest/v1" if MDPOSIT_URL else ""
MDPOSIT_VRE_LITE_URL = f"{MDPOSIT_URL}/vre_lite/" if MDPOSIT_URL else ""
MDPOSIT_TRUSTED_PARENT_HOST = "mdposit.mddbr.eu"

if not MDPOSIT_URL:
    logger.warning("MDPOSIT_URL is not set. MDPosit integration will not be available.")

METADUMP_API_URL: str | None = os.environ.get("METADUMP_API_URL")

if not METADUMP_API_URL:
    logger.warning("METADUMP_API_URL environment variable is not set. MetaDump metadata extraction will be skipped.")

# MDRepo upload Job image — injected from Helm like other sidecar images.
MDREPO_UPLOADER_IMAGE = os.environ.get("MDREPO_UPLOADER_IMAGE", "")

if not MDREPO_UPLOADER_IMAGE:
    logger.warning("MDREPO_UPLOADER_IMAGE is not set. Durable MDRepo uploads will not work.")
