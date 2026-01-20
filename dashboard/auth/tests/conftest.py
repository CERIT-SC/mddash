"""
Pytest configuration for auth service tests.

Sets required environment variables BEFORE importing auth module
to prevent startup validation errors.
"""

import os
import sys
from pathlib import Path
from typing import Generator

import pytest
from flask import Flask
from flask.testing import FlaskClient

# Add parent directory to path so we can import auth module
sys.path.insert(0, str(Path(__file__).parent.parent))

# CRITICAL: Set environment variables before auth.py is imported
# auth.py raises ValueError on import if these are missing
os.environ["JUPYTERHUB_USER"] = "testuser"
os.environ["JUPYTERHUB_CLIENT_ID"] = "test-client-id"
os.environ["JUPYTERHUB_API_TOKEN"] = "test-api-token"
os.environ["JUPYTERHUB_API_URL"] = "http://hub.test/hub/api"
os.environ["JUPYTERHUB_OAUTH_CALLBACK_URL"] = "http://localhost/oauth_callback"
os.environ["JUPYTERHUB_DEFAULT_URL"] = "/lab"
os.environ["JUPYTERHUB_SERVICE_PREFIX"] = "/user/testuser"

# Import after environment is set to prevent validation errors at import time
from auth import _sessions
from auth import app as auth_app


@pytest.fixture(scope="session", autouse=True)
def setup_env() -> None:
    """Ensure environment is set for all tests."""
    return


@pytest.fixture
def app() -> Flask:
    """Provide the auth Flask app for testing."""
    auth_app.config["TESTING"] = True
    return auth_app


@pytest.fixture
def client(app: Flask) -> FlaskClient:
    """Provide a test client for making requests."""
    return app.test_client()


@pytest.fixture
def clear_sessions() -> Generator[None, None, None]:
    """Clear session store before and after each test."""
    _sessions.clear()
    yield
    _sessions.clear()
