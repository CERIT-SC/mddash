import os
import logging
from pathlib import Path

from logging_utils import configure_logging


LOG_FORMAT = '[%(asctime)s] %(levelname)s\t%(name)s: %(message)s'
LOG_LEVEL = logging.INFO

configure_logging(LOG_FORMAT, LOG_LEVEL)

logger = logging.getLogger(__name__)


JUPYTER_USER = os.environ.get('JUPYTERHUB_USER', "")
JUPYTER_SERVER_NAME = os.environ.get('JUPYTERHUB_SERVER_NAME', "")
PREFIX = os.environ.get('JUPYTERHUB_SERVICE_PREFIX', "/")

# everything related to mddash should be also prefixed with "dash"
if PREFIX:
    PREFIX += "dash"

API_PREFIX = f"{PREFIX}/api"

DATA_DIR = Path("/mddash")
DATA_DIR.mkdir(parents=True, exist_ok=True)

NOTEBOOK_IMAGE=os.environ.get('NOTEBOOK_IMAGE', 'quay.io/jupyter/base-notebook')
GMX_IMAGE = 'cerit.io/ljocha/gromacs:2024-3-plumed-2-10-afed-pytorch-model-cv-2'
S3_CLIENT_IMAGE = 'rclone/rclone:latest'

GPU_TYPE = 'nvidia.com/mig-1g.10gb'

NAMESPACE = os.environ.get('POD_NAMESPACE', 'default')

if NAMESPACE == "default":
    logger.warning("Using default namespace. Is the POD_NAMESPACE environment variable set correctly?")

HUB_NAMESPACE = os.environ.get('HUB_NAMESPACE', NAMESPACE)

MDRUN_API_URL = f'http://mdrun-api.{HUB_NAMESPACE}.svc.cluster.local/api'

S3_ENDPOINT = os.environ.get('S3_ENDPOINT', '')
S3_BUCKET = os.environ.get('S3_BUCKET', '')
S3_ACCESS_KEY = os.environ.get('S3_ACCESS_KEY', '')
S3_SECRET_KEY = os.environ.get('S3_SECRET_KEY', '')

if not all([S3_ENDPOINT, S3_BUCKET, S3_ACCESS_KEY, S3_SECRET_KEY]):
    logger.warning("One or more S3 configuration environment variables are not set. S3 functionality may be limited.")
