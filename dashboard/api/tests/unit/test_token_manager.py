"""Unit tests for MDRepo Token Manager."""

import time
from unittest.mock import Mock, patch

import pytest
from flask import Flask
from flask import session as flask_session
from flask.sessions import SessionMixin
from token_manager import (
    MDREPO_REFRESH_TOKEN_KEY,
    MDREPO_TOKEN_EXPIRES_AT,
    MDREPO_TOKEN_KEY,
    TOKEN_REFRESH_INITIAL_DELAY,
    TOKEN_REFRESH_RETRIES,
    MDRepoTokenManager,
)


@pytest.fixture
def app() -> Flask:
    """Create a test Flask app."""
    app = Flask(__name__)
    app.config["SECRET_KEY"] = "test_secret_key"
    app.config["TESTING"] = True
    return app


@pytest.fixture
def session(app: Flask) -> SessionMixin:
    """Create a test session."""
    with app.test_request_context():
        return flask_session


class TestMDRepoTokenManager:
    """Test MDRepo Token Manager."""

    def test_init(self, session: SessionMixin) -> None:
        """Test token manager initialization."""
        manager = MDRepoTokenManager(session)
        assert manager.session is session

    def test_get_valid_token_no_token(self, session: SessionMixin) -> None:
        """Test get_valid_token when no token is present."""
        manager = MDRepoTokenManager(session)
        token = manager.get_valid_token()
        assert token is None

    def test_get_valid_token_valid_token(self, session: SessionMixin) -> None:
        """Test get_valid_token with valid token."""
        session[MDREPO_TOKEN_KEY] = "test_access_token"
        session[MDREPO_TOKEN_EXPIRES_AT] = time.time() + 3600

        manager = MDRepoTokenManager(session)
        token = manager.get_valid_token()
        assert token == "test_access_token"

    @patch("token_manager.requests.post")
    def test_get_valid_token_expired_token_refresh_success(self, mock_post: Mock, session: SessionMixin) -> None:
        """Test get_valid_token with expired token that refreshes successfully."""
        # Set up expired token
        session[MDREPO_TOKEN_KEY] = "expired_token"
        session[MDREPO_REFRESH_TOKEN_KEY] = "refresh_token"
        session[MDREPO_TOKEN_EXPIRES_AT] = time.time() - 3600

        # Mock successful refresh response
        mock_response = Mock()
        mock_response.ok = True
        mock_response.json.return_value = {
            "access_token": "new_access_token",
            "refresh_token": "new_refresh_token",
            "expires_in": 3600,
        }
        mock_post.return_value = mock_response

        manager = MDRepoTokenManager(session)
        token = manager.get_valid_token()

        assert token == "new_access_token"
        assert session[MDREPO_TOKEN_KEY] == "new_access_token"
        assert session[MDREPO_REFRESH_TOKEN_KEY] == "new_refresh_token"

    @patch("token_manager.requests.post")
    def test_get_valid_token_expired_token_refresh_failure(self, mock_post: Mock, session: SessionMixin) -> None:
        """Test get_valid_token with expired token that fails to refresh."""
        # Set up expired token
        session[MDREPO_TOKEN_KEY] = "expired_token"
        session[MDREPO_REFRESH_TOKEN_KEY] = "refresh_token"
        session[MDREPO_TOKEN_EXPIRES_AT] = time.time() - 3600

        # Mock failed refresh response
        mock_response = Mock()
        mock_response.ok = False
        mock_response.status_code = 400
        mock_response.text = "Invalid refresh token"
        mock_post.return_value = mock_response

        manager = MDRepoTokenManager(session)
        token = manager.get_valid_token()

        assert token is None
        # All token keys should be cleared
        assert MDREPO_TOKEN_KEY not in session
        assert MDREPO_REFRESH_TOKEN_KEY not in session
        assert MDREPO_TOKEN_EXPIRES_AT not in session

    def test_is_token_expired_no_expiration(self, session: SessionMixin) -> None:
        """Test is_token_expired when no expiration info is available."""
        session[MDREPO_TOKEN_KEY] = "test_token"

        manager = MDRepoTokenManager(session)
        # Should return False when no expiration info (can't verify)
        assert manager.is_token_expired() is False

    def test_is_token_expired_valid(self, session: SessionMixin) -> None:
        """Test is_token_expired with valid token."""
        session[MDREPO_TOKEN_KEY] = "test_token"
        session[MDREPO_TOKEN_EXPIRES_AT] = time.time() + 3600

        manager = MDRepoTokenManager(session)
        assert manager.is_token_expired() is False

    def test_is_token_expired_expired(self, session: SessionMixin) -> None:
        """Test is_token_expired with expired token."""
        session[MDREPO_TOKEN_KEY] = "test_token"
        session[MDREPO_TOKEN_EXPIRES_AT] = time.time() - 3600

        manager = MDRepoTokenManager(session)
        assert manager.is_token_expired() is True

    @patch("token_manager.requests.post")
    def test_refresh_token_success(self, mock_post: Mock, session: SessionMixin) -> None:
        """Test successful token refresh."""
        session[MDREPO_TOKEN_KEY] = "expired_token"
        session[MDREPO_REFRESH_TOKEN_KEY] = "refresh_token"
        session[MDREPO_TOKEN_EXPIRES_AT] = time.time() - 3600  # Expired

        # Mock successful refresh response
        mock_response = Mock()
        mock_response.ok = True
        mock_response.json.return_value = {
            "access_token": "new_access_token",
            "refresh_token": "new_refresh_token",
            "expires_in": 3600,
        }
        mock_post.return_value = mock_response

        manager = MDRepoTokenManager(session)
        result = manager.refresh_token()

        assert result is True
        assert session[MDREPO_TOKEN_KEY] == "new_access_token"
        assert session[MDREPO_REFRESH_TOKEN_KEY] == "new_refresh_token"
        assert MDREPO_TOKEN_EXPIRES_AT in session

    @patch("token_manager.requests.post")
    def test_refresh_token_no_refresh_token(self, mock_post: Mock, session: SessionMixin) -> None:
        """Test refresh when no refresh token is available."""
        manager = MDRepoTokenManager(session)
        result = manager.refresh_token()

        assert result is False
        mock_post.assert_not_called()

    @patch("token_manager.requests.post")
    def test_refresh_token_invalid_refresh_token(self, mock_post: Mock, session: SessionMixin) -> None:
        """Test refresh when refresh token is invalid."""
        session[MDREPO_TOKEN_KEY] = "expired_token"
        session[MDREPO_REFRESH_TOKEN_KEY] = "invalid_refresh_token"
        session[MDREPO_TOKEN_EXPIRES_AT] = time.time() - 3600  # Expired

        # Mock failed refresh response
        mock_response = Mock()
        mock_response.ok = False
        mock_response.status_code = 400
        mock_response.text = "Invalid refresh token"
        mock_post.return_value = mock_response

        manager = MDRepoTokenManager(session)
        result = manager.refresh_token()

        assert result is False
        # Tokens should be cleared
        assert MDREPO_TOKEN_KEY not in session
        assert MDREPO_REFRESH_TOKEN_KEY not in session

    @patch("token_manager.time.sleep")
    @patch("token_manager.requests.post")
    def test_refresh_token_with_retry(self, mock_post: Mock, mock_sleep: Mock, session: SessionMixin) -> None:
        """Test refresh with retry on temporary failure."""
        session[MDREPO_TOKEN_KEY] = "expired_token"
        session[MDREPO_REFRESH_TOKEN_KEY] = "refresh_token"
        session[MDREPO_TOKEN_EXPIRES_AT] = time.time() - 3600  # Expired

        # Mock responses: first two fail, third succeeds
        mock_response_fail = Mock()
        mock_response_fail.ok = False
        mock_response_fail.status_code = 500
        mock_response_fail.text = "Server error"

        mock_response_success = Mock()
        mock_response_success.ok = True
        mock_response_success.json.return_value = {
            "access_token": "new_access_token",
            "refresh_token": "new_refresh_token",
            "expires_in": 3600,
        }

        mock_post.side_effect = [mock_response_fail, mock_response_fail, mock_response_success]

        manager = MDRepoTokenManager(session)
        result = manager.refresh_token()

        assert result is True
        assert session[MDREPO_TOKEN_KEY] == "new_access_token"
        assert mock_post.call_count == TOKEN_REFRESH_RETRIES
        # Verify sleep was called twice (between retries)
        assert mock_sleep.call_count == TOKEN_REFRESH_RETRIES - 1
        # Verify exponential backoff: 1s, 2s (for 3 retries)
        expected_delays = [TOKEN_REFRESH_INITIAL_DELAY * (2**i) for i in range(TOKEN_REFRESH_RETRIES - 1)]
        actual_delays = [call[0][0] for call in mock_sleep.call_args_list]
        assert actual_delays == expected_delays

    @patch("token_manager.time.sleep")
    @patch("token_manager.requests.post")
    def test_refresh_token_all_retries_fail(self, mock_post: Mock, mock_sleep: Mock, session: SessionMixin) -> None:
        """Test refresh when all retries fail."""
        session[MDREPO_TOKEN_KEY] = "expired_token"
        session[MDREPO_REFRESH_TOKEN_KEY] = "refresh_token"
        session[MDREPO_TOKEN_EXPIRES_AT] = time.time() - 3600  # Expired

        # Mock failed refresh response
        mock_response = Mock()
        mock_response.ok = False
        mock_response.status_code = 500
        mock_response.text = "Server error"
        mock_post.return_value = mock_response

        manager = MDRepoTokenManager(session)
        result = manager.refresh_token()

        assert result is False
        # Should retry 3 times
        assert mock_post.call_count == TOKEN_REFRESH_RETRIES
        # Verify sleep was called twice (between retries)
        assert mock_sleep.call_count == TOKEN_REFRESH_RETRIES - 1
        # Verify exponential backoff: 1s, 2s (for 3 retries)
        expected_delays = [TOKEN_REFRESH_INITIAL_DELAY * (2**i) for i in range(TOKEN_REFRESH_RETRIES - 1)]
        actual_delays = [call[0][0] for call in mock_sleep.call_args_list]
        assert actual_delays == expected_delays

    @patch("token_manager.requests.post")
    def test_refresh_token_no_new_refresh_token(self, mock_post: Mock, session: SessionMixin) -> None:
        """Test refresh when response doesn't include new refresh token."""
        session[MDREPO_TOKEN_KEY] = "expired_token"
        session[MDREPO_REFRESH_TOKEN_KEY] = "refresh_token"
        session[MDREPO_TOKEN_EXPIRES_AT] = time.time() - 3600  # Expired

        # Mock refresh response without new refresh token
        mock_response = Mock()
        mock_response.ok = True
        mock_response.json.return_value = {"access_token": "new_access_token", "expires_in": 3600}
        mock_post.return_value = mock_response

        manager = MDRepoTokenManager(session)
        result = manager.refresh_token()

        assert result is True
        assert session[MDREPO_TOKEN_KEY] == "new_access_token"
        # Old refresh token should still be there
        assert session[MDREPO_REFRESH_TOKEN_KEY] == "refresh_token"

    def test_clear_tokens(self, session: SessionMixin) -> None:
        """Test clearing all tokens."""
        session[MDREPO_TOKEN_KEY] = "test_token"
        session[MDREPO_REFRESH_TOKEN_KEY] = "test_refresh_token"
        session[MDREPO_TOKEN_EXPIRES_AT] = time.time() + 3600

        manager = MDRepoTokenManager(session)
        manager.clear_tokens()

        assert MDREPO_TOKEN_KEY not in session
        assert MDREPO_REFRESH_TOKEN_KEY not in session
        assert MDREPO_TOKEN_EXPIRES_AT not in session

    def test_has_tokens_true(self, session: SessionMixin) -> None:
        """Test has_tokens when tokens exist."""
        session[MDREPO_TOKEN_KEY] = "test_token"

        manager = MDRepoTokenManager(session)
        assert manager.has_tokens() is True

    def test_has_tokens_false(self, session: SessionMixin) -> None:
        """Test has_tokens when no tokens exist."""
        manager = MDRepoTokenManager(session)
        assert manager.has_tokens() is False
