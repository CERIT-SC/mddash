"""Unit tests for MDRepo OAuth routes."""

from http import HTTPStatus
from unittest.mock import Mock, patch

import pytest
from flask import Flask
from flask.testing import FlaskClient
from routes.mdrepo import mdrepo_bp


@pytest.fixture
def app() -> Flask:
    """Create a test Flask app."""
    app = Flask(__name__)
    app.config["SECRET_KEY"] = "test_secret_key"
    app.config["TESTING"] = True

    # Register the blueprint
    app.register_blueprint(mdrepo_bp)

    return app


@pytest.fixture
def client(app: Flask) -> FlaskClient:
    """Create a test client."""
    return app.test_client()


class TestMDRepoRoutes:
    """Test MDRepo OAuth routes."""

    def test_get_status_no_token(self, client: FlaskClient) -> None:
        """Test status endpoint when no token is present."""
        with client.session_transaction() as sess:
            sess.clear()

        response = client.get("/dash/api/mdrepo/status")
        assert response.status_code == HTTPStatus.OK
        data = response.get_json()
        assert data["success"] is True
        assert data["data"]["authenticated"] is False

    @patch("routes.mdrepo.requests.get")
    def test_get_status_valid_token(self, mock_get: Mock, client: FlaskClient) -> None:
        """Test status endpoint with valid token."""
        mock_response = Mock()
        mock_response.status_code = HTTPStatus.OK
        mock_get.return_value = mock_response

        with client.session_transaction() as sess:
            sess["mdrepo_token"] = "test_access_token"
            sess["mdrepo_token_expires_at"] = 9999999999.0  # Far in future

        response = client.get("/dash/api/mdrepo/status")
        assert response.status_code == HTTPStatus.OK
        data = response.get_json()
        assert data["success"] is True
        assert data["data"]["authenticated"] is True

    @patch("routes.mdrepo.requests.get")
    def test_get_status_expired_token(self, mock_get: Mock, client: FlaskClient) -> None:
        """Test status endpoint with expired token."""
        mock_response = Mock()
        mock_response.status_code = 401
        mock_get.return_value = mock_response

        with client.session_transaction() as sess:
            sess["mdrepo_token"] = "test_access_token"
            sess["mdrepo_token_expires_at"] = 0.0  # Expired

        response = client.get("/dash/api/mdrepo/status")
        assert response.status_code == HTTPStatus.OK
        data = response.get_json()
        assert data["success"] is True
        assert data["data"]["authenticated"] is False
        # Token should be cleared from session
        with client.session_transaction() as sess:
            assert "mdrepo_token" not in sess

    @patch("routes.mdrepo.MDREPO_CLIENT_ID", "")
    @patch("routes.mdrepo.MDREPO_CLIENT_SECRET", "")
    @patch("routes.mdrepo.MDREPO_REDIRECT_URI", "")
    def test_initiate_auth_no_config(self, client: FlaskClient) -> None:
        """Test auth initiation when OAuth is not configured."""
        response = client.get("/dash/api/mdrepo/auth")
        assert response.status_code == HTTPStatus.SERVICE_UNAVAILABLE

    @patch("routes.mdrepo.MDREPO_CLIENT_ID", "test_client_id")
    @patch("routes.mdrepo.MDREPO_CLIENT_SECRET", "test_client_secret")
    @patch("routes.mdrepo.MDREPO_REDIRECT_URI", "http://localhost/callback")
    @patch("routes.mdrepo.MDREPO_AUTHORIZE_URL", "http://mdrepo.example.com/oauth/authorize")
    @patch("routes.mdrepo.MDREPO_SCOPES", "read write")
    def test_initiate_auth_with_config(self, client: FlaskClient) -> None:
        """Test auth initiation with proper configuration."""
        response = client.get("/dash/api/mdrepo/auth?return_url=/test")
        assert response.status_code == HTTPStatus.FOUND

        # Check that state and return_url are stored
        with client.session_transaction() as sess:
            assert "mdrepo_oauth_state" in sess
            assert sess["mdrepo_return_url"] == "/test"

    @patch("routes.mdrepo.requests.post")
    def test_oauth_callback_success(self, mock_post: Mock, client: FlaskClient) -> None:
        """Test OAuth callback with successful token exchange."""
        # Mock token response
        mock_response = Mock()
        mock_response.ok = True
        mock_response.json.return_value = {
            "access_token": "new_access_token",
            "refresh_token": "new_refresh_token",
            "expires_in": 3600,
        }
        mock_post.return_value = mock_response

        # Set up session with state and return_url
        with client.session_transaction() as sess:
            sess["mdrepo_oauth_state"] = "test_state"
            sess["mdrepo_return_url"] = "/dashboard"

        response = client.get("/dash/api/mdrepo/callback?code=test_code&state=test_state")
        assert response.status_code == HTTPStatus.FOUND

        # Check that tokens are stored
        with client.session_transaction() as sess:
            assert sess["mdrepo_token"] == "new_access_token"
            assert sess["mdrepo_refresh_token"] == "new_refresh_token"
            assert "mdrepo_token_expires_at" in sess
            # State should be cleared
            assert "mdrepo_oauth_state" not in sess

    @patch("routes.mdrepo.requests.post")
    def test_oauth_callback_no_refresh_token(self, mock_post: Mock, client: FlaskClient) -> None:
        """Test OAuth callback when refresh token is not provided."""
        # Mock token response without refresh token
        mock_response = Mock()
        mock_response.ok = True
        mock_response.json.return_value = {"access_token": "new_access_token", "expires_in": 3600}
        mock_post.return_value = mock_response

        # Set up session with state and return_url
        with client.session_transaction() as sess:
            sess["mdrepo_oauth_state"] = "test_state"
            sess["mdrepo_return_url"] = "/dashboard"

        response = client.get("/dash/api/mdrepo/callback?code=test_code&state=test_state")
        assert response.status_code == HTTPStatus.FOUND

        # Check that access token is stored but refresh token is not
        with client.session_transaction() as sess:
            assert sess["mdrepo_token"] == "new_access_token"
            assert "mdrepo_refresh_token" not in sess
            assert "mdrepo_token_expires_at" in sess

    def test_oauth_callback_error(self, client: FlaskClient) -> None:
        """Test OAuth callback with error."""
        with client.session_transaction() as sess:
            sess["mdrepo_oauth_state"] = "test_state"
            sess["mdrepo_return_url"] = "/dashboard"

        response = client.get("/dash/api/mdrepo/callback?error=access_denied&state=test_state")
        assert response.status_code == HTTPStatus.FOUND
        # Check that error parameter is in the redirect URL (URL-encoded)
        assert "mdrepo_error=" in response.location
        assert "/dashboard" in response.location

    def test_oauth_callback_invalid_state(self, client: FlaskClient) -> None:
        """Test OAuth callback with invalid state."""
        with client.session_transaction() as sess:
            sess["mdrepo_oauth_state"] = "correct_state"
            sess["mdrepo_return_url"] = "/dashboard"

        response = client.get("/dash/api/mdrepo/callback?code=test_code&state=wrong_state")
        assert response.status_code == HTTPStatus.FOUND
        assert "mdrepo_error=Invalid+state+parameter" in response.location

    @patch("routes.mdrepo.requests.post")
    def test_oauth_callback_token_exchange_failed(self, mock_post: Mock, client: FlaskClient) -> None:
        """Test OAuth callback when token exchange fails."""
        # Mock failed token response
        mock_response = Mock()
        mock_response.ok = False
        mock_response.status_code = 400
        mock_response.text = "Invalid grant"
        mock_post.return_value = mock_response

        # Set up session with state and return_url
        with client.session_transaction() as sess:
            sess["mdrepo_oauth_state"] = "test_state"
            sess["mdrepo_return_url"] = "/dashboard"

        response = client.get("/dash/api/mdrepo/callback?code=test_code&state=test_state")
        assert response.status_code == HTTPStatus.FOUND
        assert "mdrepo_error=Token+exchange+failed" in response.location

    def test_logout(self, client: FlaskClient) -> None:
        """Test logout endpoint."""
        with client.session_transaction() as sess:
            sess["mdrepo_token"] = "test_token"
            sess["mdrepo_refresh_token"] = "test_refresh_token"
            sess["mdrepo_token_expires_at"] = 9999999999.0

        response = client.post("/dash/api/mdrepo/logout")
        assert response.status_code == HTTPStatus.OK
        data = response.get_json()
        assert data["success"] is True
        assert data["data"]["message"] == "Logged out from MDRepo"

        # Check that all tokens are cleared
        with client.session_transaction() as sess:
            assert "mdrepo_token" not in sess
            assert "mdrepo_refresh_token" not in sess
            assert "mdrepo_token_expires_at" not in sess
