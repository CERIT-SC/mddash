import os
import logging
from pathlib import Path

LOG_FORMAT = '[%(asctime)s] %(levelname)s\t%(name)s: %(message)s'
logging.basicConfig(format=LOG_FORMAT, level=logging.INFO)

API_PREFIX = '/api'

DATA_DIR = Path('/data')
DATA_DIR.mkdir(parents=True, exist_ok=True)
DB_URL = f'sqlite:///{DATA_DIR}/mdrun.db'

NAMESPACE = os.environ.get('POD_NAMESPACE', 'default')
PVC_NAME = os.environ.get('PVC_NAME', 'mdrun-api-pvc')
