import os
from pathlib import Path

JUPYTER_USER = os.environ.get('JUPYTERHUB_USER', None)
PREFIX = f"/user/{JUPYTER_USER}" if JUPYTER_USER else ""

DATA_DIR = Path("/mddash/db")
STATE_FILE = DATA_DIR / "experiments.json"

API_DIR = Path(__file__).resolve().parent
FRONTEND_DIR = Path("/var/tmp/dash")

NOTEBOOK_IMAGE=os.environ.get('NOTEBOOK_IMAGE','quay.io/jupyter/base-notebook')

with open('/var/run/secrets/kubernetes.io/serviceaccount/namespace') as ns:
  NAMESPACE=ns.read().strip()
