"""
Demo harness that runs the real API with deterministic seeded data and mocked integrations.

Usage:
    python _demo/app.py   # uvicorn on :8888 (auto-reload unless MDDASH_DEMO_E2E=1)
"""

import os
import secrets
import shutil
import sys
from pathlib import Path
from typing import TYPE_CHECKING

import uvicorn

if TYPE_CHECKING:
    from fastapi import FastAPI

API_DIR = Path(__file__).resolve().parents[1]

if str(API_DIR) not in sys.path:
    sys.path.insert(0, str(API_DIR))


# Demo env defaults, applied via os.environ.setdefault so any real env still wins.
_DEMO_ENV_DEFAULTS = {
    "HOSTNAME": "localhost",
    "JUPYTERHUB_USER": "dev-user",
    "JUPYTERHUB_SERVICE_PREFIX": "/",
    "POD_NAMESPACE": "default",
    "HUB_NAMESPACE": "default",
    "PVC_NAME": "demo-pvc",
    "PVC_STORAGE_SIZE": "100Gi",
    "NS_REQUESTS_CPU": "2000m",
    "NS_REQUESTS_MEMORY": "8Gi",
    "NS_LIMITS_CPU": "14000m",
    "NS_LIMITS_MEMORY": "25Gi",
    "NS_MAX_NOTEBOOKS": "2",
    "NOTEBOOK_CPU_REQUEST": "200m",
    "NOTEBOOK_MEMORY_REQUEST": "512Mi",
    "NOTEBOOK_CPU_LIMIT": "2",
    "NOTEBOOK_MEMORY_LIMIT": "4Gi",
    "GMX_CPU_REQUEST": "100m",
    "GMX_MEMORY_REQUEST": "256Mi",
    "GMX_CPU_LIMIT": "2000m",
    "GMX_MEMORY_LIMIT": "2Gi",
    "GPU_TYPE": "nvidia.com/gpu",
    "TUNER_USER": "demo",
    "TUNER_PASSWORD": "demo",
    "S3_BUCKET": "demo-bucket",
    "MDREPO_URL": "https://workflow-repo.test.du.cesnet.cz",
    "MDREPO_SCOPES": "openid profile",
    "MDREPO_CLIENT_ID": "demo-client",
    "MDREPO_CLIENT_SECRET": "demo-secret",
    "MDREPO_UPLOADER_IMAGE": "demo-mdrepo-uploader",
    "ARCHIVE_WORKER_IMAGE": "demo-archive-worker",
    "DEFAULT_NOTEBOOKS_REPO": "https://github.com/CERIT-SC/mddash-notebooks.git",
    "MDPOSIT_URL": "https://mdposit.mddbr.eu",
}


def _configure_demo_env() -> None:
    """Configure environment variables for demo mode."""
    demo_data_dir = os.environ.get("MDDASH_DEMO_DATA_DIR", "/tmp/mddash")
    # Reset on every start (including auto-reload restarts): demo data is
    # disposable, so there is no rehydration path to keep in sync with the seed.
    shutil.rmtree(demo_data_dir, ignore_errors=True)
    Path(demo_data_dir).mkdir(parents=True, exist_ok=True)
    os.environ.setdefault("DATA_DIR", demo_data_dir)
    for key, value in _DEMO_ENV_DEFAULTS.items():
        os.environ.setdefault(key, value)


def create_demo_app() -> "FastAPI":
    """
    Create the real API app configured for local demo with mocked dependencies (uvicorn factory).

    Mocks must be installed before the app is imported: K8s is neutralized by
    patching the `K8sClient` methods, not by patching the kubernetes library.
    """
    _configure_demo_env()

    from _demo.mocks import install_all_mocks  # ruff:ignore[import-outside-top-level]
    from _demo.profile import setup_demo_profile  # ruff:ignore[import-outside-top-level]

    install_all_mocks()

    from app import create_app  # ruff:ignore[import-outside-top-level]

    # Fresh key per start: stale signed cookies die with the wiped demo data,
    # so a mock MDRepo session must be re-established after every restart.
    app = create_app(secure_cookies=False, session_secret=secrets.token_hex(32))
    setup_demo_profile(app)
    return app


if __name__ == "__main__":
    # E2E: no auto-reload — a file-watch restart would wipe and reseed demo state mid-suite.
    e2e = os.environ.get("MDDASH_DEMO_E2E") == "1"
    uvicorn.run(
        "_demo.app:create_demo_app",
        factory=True,
        host="0.0.0.0",
        port=int(os.environ.get("PORT", "8888")),
        reload=not e2e,
        reload_dirs=[str(API_DIR)],
        app_dir=str(API_DIR),
    )
