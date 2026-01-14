"""
Pytest configuration and shared fixtures for mdrun-api tests.

Provides:
- Flask test client with in-memory SQLite database
- Mocked K8s client to avoid cluster dependencies
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
_test_data_dir = tempfile.mkdtemp(prefix="mdrun_test_")

# Set test environment before importing app modules
os.environ["DATA_DIR"] = _test_data_dir
os.environ["APP_ENV"] = "test"
os.environ["S3_ENDPOINT"] = "http://s3.test:9000"
os.environ["S3_ACCESS_KEY"] = "test-access-key"
os.environ["S3_SECRET_KEY"] = "test-secret-key"


@pytest.fixture(scope="session")
def mock_k8s() -> Generator[MagicMock, None, None]:
    """
    Mock the Kubernetes client for all tests.

    Prevents any actual K8s API calls during testing.
    """
    with (
        patch("kubernetes.config.load_incluster_config"),
        patch("kubernetes.client.CoreV1Api") as mock_core_api,
        patch("kubernetes.client.BatchV1Api") as mock_batch_api,
    ):
        mock_core_api.return_value = MagicMock()
        mock_batch_api.return_value = MagicMock()
        yield mock_core_api


@pytest.fixture
def app(mock_k8s: MagicMock) -> Generator[Flask, None, None]:  # noqa: ARG001
    """
    Create a Flask application configured for testing.

    Uses an in-memory SQLite database.
    The mock_k8s fixture is required to ensure K8s is mocked before app import.
    """
    # Mock k8s_client module functions before importing app
    with (
        patch("k8s_client.create_gromacs_job") as mock_create,
        patch("k8s_client.delete_job") as mock_delete,
        patch("k8s_client.get_job_status") as mock_status,
    ):
        from enums import JobStatus

        mock_create.return_value = None
        mock_delete.return_value = None
        mock_status.return_value = JobStatus.PENDING

        from extensions import db

        # Create test app
        test_app = Flask(__name__)
        test_app.config["TESTING"] = True
        test_app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///:memory:"
        test_app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
        test_app.config["SQLALCHEMY_ENGINE_OPTIONS"] = {"connect_args": {"check_same_thread": False}}

        db.init_app(test_app)

        # Import and register blueprints
        from routes import health_bp, mdrun_bp

        test_app.register_blueprint(health_bp)
        test_app.register_blueprint(mdrun_bp)

        with test_app.app_context():
            db.create_all()
            yield test_app
            db.drop_all()


@pytest.fixture
def client(app: Flask) -> FlaskClient:
    """Provide a Flask test client for making requests."""
    return app.test_client()


@pytest.fixture
def db_session(app: Flask) -> Generator:
    """
    Provide a database session for direct model testing.

    Automatically rolls back changes after each test.
    """
    from extensions import db

    with app.app_context():
        yield db.session
        db.session.rollback()


@pytest.fixture
def mock_k8s_client(mocker: MockerFixture) -> dict[str, MagicMock]:
    """
    Mock individual k8s_client functions for fine-grained control.

    Returns dict of mock objects for assertions.
    """
    from enums import JobStatus

    return {
        "create_gromacs_job": mocker.patch("k8s_client.create_gromacs_job"),
        "delete_job": mocker.patch("k8s_client.delete_job"),
        "get_job_status": mocker.patch("k8s_client.get_job_status", return_value=JobStatus.PENDING),
    }
