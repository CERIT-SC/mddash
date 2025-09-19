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

# Parse S3 credentials from S3_CREDENTIALS environment variable
def parse_s3_credentials():
    """Parse S3 credentials from environment variable containing export statements."""
    s3_creds = os.environ.get('S3_CREDENTIALS', '')
    
    if not s3_creds:
        raise ValueError("S3_CREDENTIALS environment variable is not set")

    access_key = None
    secret_key = None

    lines = s3_creds.split('\n')
    for line in lines:
        if 'MINIO_ROOT_USER=' in line and '"' in line:
            access_key = line.split('"')[1]
        elif 'MINIO_ROOT_PASSWORD=' in line and '"' in line:
            secret_key = line.split('"')[1]
    
    if not access_key or not secret_key:
        raise ValueError("Could not parse S3_ACCESS_KEY and S3_SECRET_KEY from S3_CREDENTIALS")
    
    return access_key, secret_key

# Get S3 info
S3_ENDPOINT = os.environ.get('S3_ENDPOINT', None)

try:
    S3_ACCESS_KEY, S3_SECRET_KEY = parse_s3_credentials()
except (ValueError, IndexError) as e:
    logging.warning(f"S3 credentials parsing failed: {e}")
    S3_ACCESS_KEY = None
    S3_SECRET_KEY = None
