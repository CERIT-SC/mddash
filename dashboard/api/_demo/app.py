"""
Demo harness that runs the real API with deterministic seeded data and mocked integrations.

This module provides a Flask application factory that:
- Sets up demo environment variables
- Activates HTTP response mocking via the responses library
- Patches Kubernetes client at module level
- Seeds the database with deterministic test data

Usage:
    # Run directly for development
    python -m _demo.app

    # Or in Flask development mode
    FLASK_APP=_demo.app flask run
"""

import os
import shutil
import sys
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from flask import Flask

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
    "DEFAULT_NOTEBOOKS_REPO": "https://github.com/sb-ncbr/mddash-notebooks.git",
    "MDPOSIT_URL": "https://mdposit.mddbr.eu",
}


def _configure_demo_env() -> None:
    """Configure environment variables for demo mode."""
    demo_data_dir = os.environ.get("MDDASH_DEMO_DATA_DIR", "/tmp/mddash")
    # Reset on every start (including debug-reloader restarts): demo data is
    # disposable, so there is no rehydration path to keep in sync with the seed.
    shutil.rmtree(demo_data_dir, ignore_errors=True)
    Path(demo_data_dir).mkdir(parents=True, exist_ok=True)
    os.environ.setdefault("DATA_DIR", demo_data_dir)
    for key, value in _DEMO_ENV_DEFAULTS.items():
        os.environ.setdefault(key, value)


def create_demo_app() -> "Flask":
    """
    Create the real API app configured for local demo with mocked dependencies.

    This function:
    1. Configures environment variables for demo mode
    2. Activates HTTP response mocking via responses library
    3. Installs Kubernetes client mocks via module mutation
    4. Imports and configures the real Flask application
    5. Seeds deterministic test data

    Returns:
        Configured Flask application instance with demo profile applied.
    """
    _configure_demo_env()

    # K8s is neutralized by clients.k8s module mutation, not by patching the
    # kubernetes library — mocks must be installed before the app is imported.
    from _demo.mocks import install_all_mocks  # ruff:ignore[import-outside-top-level]
    from _demo.profile import setup_demo_profile  # ruff:ignore[import-outside-top-level]

    install_all_mocks()

    from app import create_app  # ruff:ignore[import-outside-top-level]

    app = create_app()

    setup_demo_profile(app)

    return app


# Create the demo app instance
app = create_demo_app()


if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=8888)
