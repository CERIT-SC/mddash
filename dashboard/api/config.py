import os
from pathlib import Path

JUPYTER_USER = os.environ.get('JUPYTERHUB_USER', "")
JUPYTER_SERVER_NAME = os.environ.get('JUPYTERHUB_SERVER_NAME', "")
PREFIX = os.environ.get('JUPYTERHUB_SERVICE_PREFIX', "")

# everything related to mddash should be also prefixed with "dash"
if PREFIX:
    PREFIX += "dash"

DATA_DIR = Path("/mddash")
STATE_FILE = DATA_DIR / "experiments.json"

API_DIR = Path(__file__).resolve().parent
FRONTEND_DIR = Path("/var/tmp/dash")

NOTEBOOK_IMAGE=os.environ.get('NOTEBOOK_IMAGE', 'quay.io/jupyter/base-notebook')


NAMESPACE = os.environ.get('POD_NAMESPACE', 'default')

if NAMESPACE == "default":
    print("⚠️ Warning: Using default namespace. Is the POD_NAMESPACE environment variable set correctly?")

PVC_NAME = f"claim-{JUPYTER_USER}{JUPYTER_SERVER_NAME}"
