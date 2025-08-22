import os
import logging
from pathlib import Path

LOG_FORMAT = '[%(asctime)s] %(levelname)s\t%(name)s: %(message)s'
logging.basicConfig(format=LOG_FORMAT, level=logging.INFO)

DATABASE_URL = os.environ.get('DATABASE_URL', 'sqlite:///mdrun.db')
NAMESPACE = os.environ.get('POD_NAMESPACE', 'default')
PVC_NAME = os.environ.get('PVC_NAME', 'data-pvc')

DATA_DIR = Path(os.environ.get('DATA_DIR', '/data'))
DATA_DIR.mkdir(parents=True, exist_ok=True)

API_PREFIX = '/api/v1'
