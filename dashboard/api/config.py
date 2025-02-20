import os
from pathlib import Path

JUPYTER_USER = os.environ.get('JUPYTERHUB_USER', None)
PREFIX = f"/user/{JUPYTER_USER}" if JUPYTER_USER else ""

BASE_DIR = Path(__file__).resolve().parent

DATA_DIR = Path("/home/jovyan/work/data")
STATE_FILE = DATA_DIR / "experiments.json"

FRONTEND_DIR = Path("/var/tmp/dash")
