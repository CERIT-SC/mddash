import json
import logging
import os
from pathlib import Path

APP_ENV = os.getenv("APP_ENV", "prod")
IS_DEV = APP_ENV == "dev"

LOG_FORMAT = "[%(asctime)s] %(levelname)s\t%(name)s: %(message)s"
LOG_LEVEL = logging.DEBUG if IS_DEV else logging.INFO
logging.basicConfig(format=LOG_FORMAT, level=LOG_LEVEL)

API_PREFIX = "/api"

DATA_DIR = Path(os.environ.get("DATA_DIR", "/data"))
DATA_DIR.mkdir(parents=True, exist_ok=True)
DB_URL = f"sqlite:///{DATA_DIR}/mdrun.db?timeout=30"

NAMESPACE = os.environ.get("POD_NAMESPACE", "default")
PVC_NAME = os.environ.get("PVC_NAME", "mdrun-api-pvc")


def _json_env(name: str) -> object | None:
    """
    Read a JSON-encoded environment variable.

    Malformed JSON is a deployment misconfiguration, so it fails at startup
    rather than on the first job creation.
    """
    raw = os.environ.get(name)
    if not raw:
        return None
    try:
        return json.loads(raw)
    except json.JSONDecodeError as exc:
        msg = f"{name} must be valid JSON: {exc}"
        raise RuntimeError(msg) from exc


# Optional scheduling overrides for simulation Job pods, used to offload them
# to nodes outside the regular scheduler (e.g. interLink virtual nodes backed
# by HPC/SLURM). JOB_NODE_SELECTOR becomes the pod spec's nodeSelector (a
# string-to-string map), JOB_TOLERATIONS its tolerations (a list of maps).
# Unset (default) = no overrides: jobs schedule anywhere and the manifest is
# identical to a plain-K8s deployment.
JOB_NODE_SELECTOR = _json_env("JOB_NODE_SELECTOR")
JOB_TOLERATIONS = _json_env("JOB_TOLERATIONS")

GPU_TYPE = os.environ.get("GPU_TYPE", "")

S3_ENDPOINT = os.environ.get("S3_ENDPOINT")
S3_ACCESS_KEY = os.environ.get("S3_ACCESS_KEY")
S3_SECRET_KEY = os.environ.get("S3_SECRET_KEY")

GMX_IMAGE = os.environ.get("GMX_IMAGE", "")
AMBER_IMAGE = os.environ.get("AMBER_IMAGE", "")

logger = logging.getLogger(__name__)

if not all([S3_ENDPOINT, S3_ACCESS_KEY, S3_SECRET_KEY]):
    logger.error("S3_ACCESS_KEY, S3_SECRET_KEY or S3_ENDPOINT are not set!")

if not GMX_IMAGE:
    logger.warning("GMX_IMAGE environment variable is not set. GROMACS jobs will not work.")

if not AMBER_IMAGE:
    logger.warning("AMBER_IMAGE environment variable is not set. AMBER jobs will not work.")
