import os
from pathlib import Path

JUPYTER_USER = os.environ.get('JUPYTERHUB_USER', None)
ROOT_PATH = f"/user/{JUPYTER_USER}/dash/api" if JUPYTER_USER else ""

BASE_DIR = Path(__file__).resolve().parent

DATA_DIR = Path("/home/jovyan/work/data")
STATE_FILE = DATA_DIR / "experiments.json"
