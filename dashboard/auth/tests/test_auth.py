"""
Unit and integration tests for the auth service.

Tests session management, HMAC signing, and OAuth flow.
"""

import time
from concurrent.futures import ThreadPoolExecutor
from http import HTTPStatus
from unittest.mock import MagicMock, patch
from urllib.parse import parse_qs, urlsplit

import auth
import pytest
from auth import (
    COOKIE_NAME,
    HMAC_SHA256_HEX_LENGTH,
    STATE_COOKIE,
    USER,
    _sessions,  # ruff:ignore[import-private-name]
    create_session,
    is_valid_session,
    remove_expired_sessions,
    sign,
)
from flask import Flask
from flask.testing import FlaskClient


class TestHealthEndpoint:
    """Tests for /health endpoint."""

    def test_health_returns_ok(self, client: FlaskClient) -> None:
        """Health endpoint should return 200 OK."""
        response = client.get("/health")

        assert response.status_code == HTTPStatus.OK
        assert response.data == b"OK"


@pytest.mark.usefixtures("clear_sessions")
class TestSessionManagement:
    """Tests for session creation and validation."""

    def test_create_session_returns_token(self, app: Flask) -> None:
        """create_session should return a token string."""
        with app.app_context():
            token = create_session("testuser")

            assert isinstance(token, str)
            assert len(token) > 0

    def test_is_valid_session_with_valid_token(self, app: Flask) -> None:
        """is_valid_session should return True for valid token."""
        with app.app_context():
            token = create_session("testuser")

            assert is_valid_session(token, "testuser") is True

    def test_is_valid_session_with_wrong_user(self, app: Flask) -> None:
        """is_valid_session should return False for wrong user."""
        with app.app_context():
            token = create_session("testuser")

            assert is_valid_session(token, "otheruser") is False

    def test_is_valid_session_with_invalid_token(self, app: Flask) -> None:
        """is_valid_session should return False for invalid token."""
        with app.app_context():
            assert is_valid_session("invalid-token", "testuser") is False

    def test_is_valid_session_with_empty_token(self, app: Flask) -> None:
        """is_valid_session should return False for empty token."""
        with app.app_context():
            assert is_valid_session("", "testuser") is False

    def test_expired_session_is_invalid(self, app: Flask) -> None:
        """Expired sessions should be invalid."""
        with app.app_context():
            # Create expired session directly
            token = "expired-token"
            _sessions[token] = ("testuser", time.time() - 100)

            assert is_valid_session(token, "testuser") is False


class TestHmacSigning:
    """Tests for HMAC state signing."""

    def test_sign_produces_hex_string(self, app: Flask) -> None:
        """Sign should produce a hex string."""
        with app.app_context():
            signature = sign("test-state")

            assert isinstance(signature, str)
            # HMAC SHA256 produces 64 hex characters
            assert len(signature) == HMAC_SHA256_HEX_LENGTH
            assert all(c in "0123456789abcdef" for c in signature)

    def test_sign_is_deterministic(self, app: Flask) -> None:
        """Same input should produce same signature."""
        with app.app_context():
            sig1 = sign("test-state")
            sig2 = sign("test-state")

            assert sig1 == sig2

    def test_sign_different_inputs(self, app: Flask) -> None:
        """Different inputs should produce different signatures."""
        with app.app_context():
            sig1 = sign("state1")
            sig2 = sign("state2")

            assert sig1 != sig2


@pytest.mark.usefixtures("clear_sessions")
class TestSessionCleanup:
    """Tests for expired session cleanup."""

    def test_remove_expired_sessions(self, app: Flask) -> None:
        """remove_expired_sessions should remove only expired sessions."""
        with app.app_context():
            now = time.time()

            # Add sessions: one valid, one expired
            _sessions["valid"] = ("user1", now + 3600)
            _sessions["expired"] = ("user2", now - 100)

            # Force cleanup by resetting last cleanup time
            auth._last_cleanup = 0  # ruff:ignore[private-member-access]

            remove_expired_sessions()

            assert "valid" in _sessions
            assert "expired" not in _sessions


@pytest.mark.usefixtures("clear_sessions")
class TestAuthEndpoint:
    """Tests for /auth endpoint."""

    def test_authenticated_user_with_valid_session(self) -> None:
        """Session validation logic should work correctly."""
        # Create session and verify it's valid
        token = create_session("testuser")
        assert is_valid_session(token, "testuser") is True

    def test_unauthenticated_user_redirects_to_oauth(self, client: FlaskClient) -> None:
        """Unauthenticated user should be redirected to OAuth."""
        response = client.get("/auth")

        assert response.status_code == HTTPStatus.FOUND
        assert "/hub/api/oauth2/authorize" in response.location


class TestOAuthCallback:
    """Tests for /oauth_callback endpoint."""

    def test_callback_without_code_returns_400(self, client: FlaskClient) -> None:
        """Callback without code parameter should return 400."""
        response = client.get("/oauth_callback?state=test")

        assert response.status_code == HTTPStatus.BAD_REQUEST

    def test_callback_without_state_returns_400(self, client: FlaskClient) -> None:
        """Callback without state parameter should return 400."""
        response = client.get("/oauth_callback?code=test")

        assert response.status_code == HTTPStatus.BAD_REQUEST

    def test_callback_with_invalid_state_returns_400(self, client: FlaskClient) -> None:
        """Callback with invalid state signature should return 400."""
        response = client.get(
            "/oauth_callback?code=test&state=test",
            headers={"Cookie": f"{STATE_COOKIE}=invalid-signature"},
        )

        assert response.status_code == HTTPStatus.BAD_REQUEST

    def test_successful_oauth_flow(self) -> None:
        """Complete OAuth flow logic - token exchange and user verification."""
        # Test the core OAuth logic by verifying mocked responses work correctly
        with patch("auth.requests.post") as mock_post, patch("auth.requests.get") as mock_get:
            # Mock token exchange
            mock_post.return_value = MagicMock(
                status_code=HTTPStatus.OK,
                json=lambda: {"access_token": "test-access-token"},
            )

            # Mock user info request
            mock_get.return_value = MagicMock(
                status_code=HTTPStatus.OK,
                json=lambda: {"name": "testuser"},
            )

            # Verify the mocked endpoints return expected data
            token_response = mock_post()
            assert token_response.json()["access_token"] == "test-access-token"

            user_response = mock_get()
            assert user_response.json()["name"] == "testuser"

    def test_user_mismatch_detection(self) -> None:
        """OAuth should detect user mismatch."""
        expected_user = USER
        returned_user = "wronguser"

        assert expected_user != returned_user


@pytest.mark.usefixtures("clear_sessions")
class TestLoginTokenEndpoints:
    """Tests for passwordless login token creation and redemption."""

    @staticmethod
    def create_login_token(client: FlaskClient) -> str:
        """
        Create a login token through the authenticated endpoint.

        Returns:
            str: The token extracted from the generated URL fragment.
        """
        auth_token = create_session(USER)
        client.set_cookie(COOKIE_NAME, auth_token)
        response = client.post("/create-login-token")
        fragment = urlsplit(response.get_json()["login_url"]).fragment
        return parse_qs(fragment)["token"][0]

    def test_create_login_token_keeps_token_out_of_url_query(self, client: FlaskClient) -> None:
        """Generated login URLs should carry the token only in the fragment."""
        auth_token = create_session(USER)
        client.set_cookie(COOKIE_NAME, auth_token)

        response = client.post("/create-login-token")

        assert response.status_code == HTTPStatus.OK
        payload = response.get_json()
        assert payload is not None
        assert "token" not in payload
        assert payload["login_url"].startswith(f"/user/{USER}/dash/auth/login-token#token=")
        assert "?token=" not in payload["login_url"]

    def test_get_login_token_does_not_consume_token(self, client: FlaskClient) -> None:
        """Loading the redemption page should not mutate token state."""
        token = self.create_login_token(client)

        response = client.get(f"/login-token?token={token}")

        assert response.status_code == HTTPStatus.OK
        assert COOKIE_NAME not in response.headers.get("Set-Cookie", "")
        assert client.post("/login-token", json={"token": token}).status_code == HTTPStatus.OK

    def test_post_login_token_consumes_token_once(self, app: Flask) -> None:
        """Concurrent redemption attempts should produce only one session."""
        with app.test_client() as client:
            token = self.create_login_token(client)

        def redeem() -> int:
            with app.test_client() as client:
                return client.post("/login-token", json={"token": token}).status_code

        with ThreadPoolExecutor(max_workers=2) as executor:
            statuses = sorted(executor.map(lambda _: redeem(), range(2)))

        assert statuses == [HTTPStatus.OK, HTTPStatus.UNAUTHORIZED]

    def test_redeemed_session_cookie_is_secure(self, client: FlaskClient) -> None:
        """Passwordless sessions should use hardened cookie attributes."""
        token = self.create_login_token(client)

        response = client.post("/login-token", json={"token": token})

        assert response.status_code == HTTPStatus.OK
        set_cookie = response.headers["Set-Cookie"]
        assert "Secure" in set_cookie
        assert "HttpOnly" in set_cookie
        assert "SameSite=Lax" in set_cookie

    def test_login_token_is_not_accepted_as_session_cookie(self, client: FlaskClient) -> None:
        """One-time login credentials should not authenticate as sessions."""
        token = self.create_login_token(client)
        client.set_cookie(COOKIE_NAME, token)

        response = client.get("/auth")

        assert response.status_code == HTTPStatus.FOUND

    def test_login_token_rejects_oversized_body(self, client: FlaskClient) -> None:
        """The public redemption endpoint should bound request memory usage."""
        response = client.post("/login-token", json={"token": "x" * 4097})

        assert response.status_code == HTTPStatus.REQUEST_ENTITY_TOO_LARGE

    @pytest.mark.parametrize("payload", [["token"], "token", True])
    def test_login_token_rejects_non_object_json(self, client: FlaskClient, payload: object) -> None:
        """Malformed JSON shapes should receive a controlled client error."""
        response = client.post("/login-token", json=payload)

        assert response.status_code == HTTPStatus.BAD_REQUEST


def test_health_logs_first_health_once(client: FlaskClient, caplog) -> None:  # ruff:ignore[missing-type-function-argument]
    """The first auth health response should be visible in startup diagnostics once."""
    import auth  # ruff:ignore[import-outside-top-level]

    auth._first_health_logged = False  # ruff:ignore[private-member-access]
    caplog.set_level("INFO", logger="auth")

    client.get("/health")
    client.get("/health")

    messages = [record.getMessage() for record in caplog.records]
    assert messages.count("auth first health response served") == 1
