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
import sys
from pathlib import Path
from typing import TYPE_CHECKING
from unittest.mock import patch

if TYPE_CHECKING:
    from flask import Flask

API_DIR = Path(__file__).resolve().parents[1]

if str(API_DIR) not in sys.path:
    sys.path.insert(0, str(API_DIR))


def _configure_demo_env() -> None:
    """Configure environment variables for demo mode."""
    demo_data_dir = os.environ.get("MDDASH_DEMO_DATA_DIR", "/tmp/mddash")
    os.environ.setdefault("DATA_DIR", demo_data_dir)
    os.environ.setdefault("HOSTNAME", "localhost")
    os.environ.setdefault("JUPYTERHUB_USER", "dev-user")
    os.environ.setdefault("JUPYTERHUB_SERVICE_PREFIX", "/")
    os.environ.setdefault("POD_NAMESPACE", "default")
    os.environ.setdefault("HUB_NAMESPACE", "default")
    os.environ.setdefault("PVC_NAME", "demo-pvc")
    os.environ.setdefault("PVC_STORAGE_SIZE", "100Gi")
    os.environ.setdefault("NS_REQUESTS_CPU", "2000m")
    os.environ.setdefault("NS_REQUESTS_MEMORY", "8Gi")
    os.environ.setdefault("NS_LIMITS_CPU", "14000m")
    os.environ.setdefault("NS_LIMITS_MEMORY", "25Gi")
    os.environ.setdefault("NOTEBOOK_CPU_REQUEST", "200m")
    os.environ.setdefault("NOTEBOOK_MEMORY_REQUEST", "512Mi")
    os.environ.setdefault("NOTEBOOK_CPU_LIMIT", "2")
    os.environ.setdefault("NOTEBOOK_MEMORY_LIMIT", "4Gi")
    os.environ.setdefault("GMX_CPU_REQUEST", "100m")
    os.environ.setdefault("GMX_MEMORY_REQUEST", "256Mi")
    os.environ.setdefault("GMX_CPU_LIMIT", "2000m")
    os.environ.setdefault("GMX_MEMORY_LIMIT", "2Gi")
    os.environ.setdefault("GPU_TYPE", "nvidia.com/gpu")
    os.environ.setdefault("TUNER_USER", "demo")
    os.environ.setdefault("TUNER_PASSWORD", "demo")
    os.environ.setdefault("S3_BUCKET", "demo-bucket")
    os.environ.setdefault("MDREPO_URL", "https://workflow-repo.test.du.cesnet.cz")
    os.environ.setdefault("MDREPO_SCOPES", "openid profile")
    os.environ.setdefault("MDREPO_CLIENT_ID", "demo-client")
    os.environ.setdefault("MDREPO_CLIENT_SECRET", "demo-secret")
    os.environ.setdefault("DEFAULT_NOTEBOOKS_REPO", "https://github.com/sb-ncbr/mddash-notebooks.git")
    os.environ.setdefault("MDPOSIT_URL", "https://mdposit.mddbr.eu")


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

    # k8s loads kubernetes lazily; patches must precede demo seeding.
    with (
        patch("kubernetes.config.load_incluster_config"),
        patch("kubernetes.client.CoreV1Api"),
        patch("kubernetes.client.BatchV1Api"),
    ):
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
