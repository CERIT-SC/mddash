import os
from pathlib import Path

JUPYTER_USER = os.environ.get('JUPYTERHUB_USER', "")
JUPYTER_SERVER_NAME = os.environ.get('JUPYTERHUB_SERVER_NAME', "")
PREFIX = os.environ.get('JUPYTERHUB_SERVICE_PREFIX', "")

DATA_DIR = Path("/mddash")
STATE_FILE = DATA_DIR / "experiments.json"

API_DIR = Path(__file__).resolve().parent
FRONTEND_DIR = Path("/var/tmp/dash")

NOTEBOOK_IMAGE=os.environ.get('NOTEBOOK_IMAGE', 'quay.io/jupyter/base-notebook')


NAMESPACE = os.environ.get('POD_NAMESPACE')

if not NAMESPACE:
    print("⚠️ POD_NAMESPACE environment variable is not set. Defaulting to 'default'.")
    NAMESPACE = "default"

PVC_NAME = f"claim-{JUPYTER_USER}{JUPYTER_SERVER_NAME}"
