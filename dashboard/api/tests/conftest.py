"""
Pytest configuration and shared fixtures for dashboard API tests.

This module provides:
- Flask test client with in-memory SQLite database
- Mocked K8s client to avoid cluster dependencies
- Mocked external HTTP requests (mdrun-api, tuner, etc.)
- SQLAlchemy session fixtures with automatic cleanup
"""

import os
import sys
import tempfile
from pathlib import Path
from typing import Generator
from unittest.mock import MagicMock, patch

import pytest
from flask import Flask
from flask.testing import FlaskClient
from pytest_mock import MockerFixture

# Add parent directory to path so we can import app modules
sys.path.insert(0, str(Path(__file__).parent.parent))

# Create a temporary directory for DATA_DIR BEFORE config.py is imported
_test_data_dir = tempfile.mkdtemp(prefix="mddash_test_")

# Set environment variables BEFORE importing app modules
# This prevents config.py from failing on missing K8s setup
os.environ["DATA_DIR"] = _test_data_dir
os.environ["JUPYTERHUB_USER"] = "testuser"
os.environ["POD_NAMESPACE"] = "test-namespace"
os.environ["HUB_NAMESPACE"] = "test-hub-namespace"
os.environ["PVC_NAME"] = "test-pvc"
os.environ["PVC_STORAGE_SIZE"] = "1Gi"
os.environ["TUNER_USER"] = "tuner"
os.environ["TUNER_PASSWORD"] = "secret"

# Mock K8s configuration to prevent failure during module import
with (
    patch("kubernetes.config.load_incluster_config"),
    patch("kubernetes.client.CoreV1Api"),
    patch("kubernetes.client.BatchV1Api"),
):
    from errors import register_error_handlers
    from extensions import db, ma
    from routes import (
        amber_bp,
        analysis_bp,
        experiments_bp,
        files_bp,
        gmx_bp,
        mdrepo_bp,
        misc_bp,
        notebook_bp,
        notebook_config_bp,
        simulations_bp,
        tuner_bp,
    )


@pytest.fixture(scope="session")
def mock_k8s() -> Generator[MagicMock, None, None]:
    """
    Mock the Kubernetes client for all tests.

    This prevents any actual K8s API calls during testing.

    Yields:
        MagicMock: The mocked CoreV1Api class.
    """
    with (
        patch("kubernetes.config.load_incluster_config"),
        patch("kubernetes.client.CoreV1Api") as mock_core_api,
        patch("kubernetes.client.BatchV1Api") as mock_batch_api,
        patch("kubernetes.client.RbacAuthorizationV1Api") as mock_rbac_api,
    ):
        # Configure mock returns
        mock_core_api.return_value = MagicMock()
        mock_batch_api.return_value = MagicMock()
        mock_rbac_api.return_value = MagicMock()
        yield mock_core_api


@pytest.fixture
def app(mock_k8s: MagicMock, tmp_path: Path) -> Generator[Flask, None, None]:
    """
    Create a Flask application configured for testing.

    Uses an in-memory SQLite database and temporary data directory.
    The mock_k8s fixture is required to ensure K8s is mocked before app import.

    Yields:
        Flask: The configured test application instance.
    """
    # Create a fresh app for each test
    test_app = Flask(__name__)
    test_app.config["TESTING"] = True
    test_app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///:memory:"
    test_app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
    test_app.config["SECRET_KEY"] = "test-secret-key"

    db.init_app(test_app)
    ma.init_app(test_app)

    # Patch DATA_DIR and import routes with the patch active
    with (
        patch.dict("config.__dict__", {"DATA_DIR": tmp_path}),
        patch("models.analysis_job.DATA_DIR", tmp_path),
        patch("models.simulation.DATA_DIR", tmp_path),
    ):
        # Register blueprints
        test_app.register_blueprint(experiments_bp)
        test_app.register_blueprint(notebook_bp)
        test_app.register_blueprint(notebook_config_bp)
        test_app.register_blueprint(analysis_bp)
        test_app.register_blueprint(tuner_bp)
        test_app.register_blueprint(gmx_bp)
        test_app.register_blueprint(amber_bp)
        test_app.register_blueprint(files_bp)
        test_app.register_blueprint(misc_bp)
        test_app.register_blueprint(mdrepo_bp)
        test_app.register_blueprint(simulations_bp)
        register_error_handlers(test_app)

        with test_app.app_context():
            db.create_all()
            yield test_app
            db.drop_all()


@pytest.fixture
def client(app: Flask) -> FlaskClient:
    """
    Provide a Flask test client for making requests.

    Returns:
        FlaskClient: A test client bound to the test application.
    """
    return app.test_client()


@pytest.fixture
def db_session(app: Flask) -> Generator:
    """
    Provide a database session for direct model testing.

    Automatically rolls back changes after each test.

    Yields:
        Generator: The active SQLAlchemy session.
    """
    with app.app_context():
        yield db.session
        db.session.rollback()


@pytest.fixture
def mock_requests(mocker: MockerFixture) -> tuple:
    """
    Mock the requests library for external HTTP calls.

    Use this to simulate responses from:
    - RCSB PDB API
    - Zenodo API
    - mdrun-api
    - Tuner API

    Returns:
        tuple: A pair of (mock_get, mock_post) patch objects.
    """
    return mocker.patch("requests.get"), mocker.patch("requests.post")


@pytest.fixture
def sample_pdb_content() -> bytes:
    """
    Return minimal valid PDB file content for testing.

    Returns:
        bytes: Minimal valid PDB file bytes for use in upload tests.
    """
    return b"""HEADER    TEST PROTEIN
ATOM      1  N   ALA A   1       0.000   0.000   0.000  1.00  0.00           N
ATOM      2  CA  ALA A   1       1.458   0.000   0.000  1.00  0.00           C
ATOM      3  C   ALA A   1       2.009   1.420   0.000  1.00  0.00           C
ATOM      4  O   ALA A   1       1.251   2.390   0.000  1.00  0.00           O
END
"""
