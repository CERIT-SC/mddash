import os
import logging
from pathlib import Path


LOG_FORMAT = '[%(asctime)s] %(levelname)s\t%(name)s: %(message)s'
logging.basicConfig(format=LOG_FORMAT, level=logging.INFO)
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)


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


NAMESPACE = os.environ.get('POD_NAMESPACE', 'default')

if NAMESPACE == "default":
    logger.warning("Using default namespace. Is the POD_NAMESPACE environment variable set correctly?")

PVC_NAME = f"claim-{JUPYTER_USER}{JUPYTER_SERVER_NAME}"
