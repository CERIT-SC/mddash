"""Demo harness that runs the real API with deterministic seeded data and mocked integrations."""

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
    os.environ.setdefault("TUNER_USER", "demo")
    os.environ.setdefault("TUNER_PASSWORD", "demo")
    os.environ.setdefault("S3_BUCKET", "demo-bucket")
    os.environ.setdefault("MDREPO_URL", "https://workflow-repo.test.du.cesnet.cz")
    os.environ.setdefault("MDREPO_SCOPES", "openid profile")
    os.environ.setdefault("MDREPO_CLIENT_ID", "demo-client")
    os.environ.setdefault("MDREPO_CLIENT_SECRET", "demo-secret")


def create_demo_app() -> "Flask":
    """
    Create the real API app configured for local demo with mocked dependencies.

    Returns:
        Flask: Configured Flask application instance with demo profile applied.
    """
    _configure_demo_env()

    with (
        patch("kubernetes.config.load_incluster_config"),
        patch("kubernetes.client.CoreV1Api"),
        patch("kubernetes.client.BatchV1Api"),
    ):
        from app import app  # noqa: PLC0415

        from _demo.profile import setup_demo_profile  # noqa: PLC0415

    setup_demo_profile(app)
    return app


app = create_demo_app()


if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=8888)
