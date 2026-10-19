"""Unit tests for MDRepo Token Manager."""

import time
from collections.abc import Iterator
from typing import Any
from unittest.mock import AsyncMock, Mock, patch

import httpx
import pytest
import respx
from modules.mdrepo.tokens import (
    MDREPO_REFRESH_TOKEN_KEY,
    MDREPO_TOKEN_EXPIRES_AT,
    MDREPO_TOKEN_KEY,
    TOKEN_REFRESH_INITIAL_DELAY,
    TOKEN_REFRESH_RETRIES,
    MDRepoTokenManager,
)

TOKEN_URL = "https://mdrepo.test/oauth/token"
SessionMixin = dict[str, Any]


@pytest.fixture(autouse=True)
def _token_url() -> Iterator[None]:
    with patch("modules.mdrepo.tokens.MDREPO_TOKEN_URL", TOKEN_URL):
        yield


@pytest.fixture
def session() -> SessionMixin:
    """Provide a request session (a plain mutable mapping)."""
    return {}


@pytest.fixture
def mock_post(http_mock: respx.MockRouter) -> Mock:
    """Mock the token endpoint; tests set `.side_effect` / `.return_value` to httpx responses."""
    endpoint = Mock()
    http_mock.post(TOKEN_URL).mock(side_effect=endpoint)
    return endpoint


@pytest.fixture
def mock_sleep() -> Iterator[AsyncMock]:
    with patch("modules.mdrepo.tokens.asyncio.sleep", AsyncMock()) as sleep:
        yield sleep


class TestMDRepoTokenManager:
    """Test MDRepo Token Manager."""

    async def test_init(self, session: SessionMixin) -> None:
        """Test token manager initialization."""
        manager = MDRepoTokenManager(session)
        assert manager.session is session

    async def test_get_valid_token_no_token(self, session: SessionMixin) -> None:
        """Test get_valid_token when no token is present."""
        manager = MDRepoTokenManager(session)
        token = await manager.get_valid_token()
        assert token is None

    async def test_get_valid_token_valid_token(self, session: SessionMixin) -> None:
        """Test get_valid_token with valid token."""
        session[MDREPO_TOKEN_KEY] = "test_access_token"
        session[MDREPO_TOKEN_EXPIRES_AT] = time.time() + 3600

        manager = MDRepoTokenManager(session)
        token = await manager.get_valid_token()
        assert token == "test_access_token"

    async def test_get_valid_token_expired_token_refresh_success(self, mock_post: Mock, session: SessionMixin) -> None:
        """Test get_valid_token with expired token that refreshes successfully."""
        # Set up expired token
        session[MDREPO_TOKEN_KEY] = "expired_token"
        session[MDREPO_REFRESH_TOKEN_KEY] = "refresh_token"
        session[MDREPO_TOKEN_EXPIRES_AT] = time.time() - 3600

        # Mock successful refresh response
        mock_post.return_value = httpx.Response(
            200, json={"access_token": "new_access_token", "refresh_token": "new_refresh_token", "expires_in": 3600}
        )

        manager = MDRepoTokenManager(session)
        token = await manager.get_valid_token()

        assert token == "new_access_token"
        assert session[MDREPO_TOKEN_KEY] == "new_access_token"
        assert session[MDREPO_REFRESH_TOKEN_KEY] == "new_refresh_token"

    async def test_get_valid_token_expired_token_refresh_failure(self, mock_post: Mock, session: SessionMixin) -> None:
        """Test get_valid_token with expired token that fails to refresh."""
        # Set up expired token
        session[MDREPO_TOKEN_KEY] = "expired_token"
        session[MDREPO_REFRESH_TOKEN_KEY] = "refresh_token"
        session[MDREPO_TOKEN_EXPIRES_AT] = time.time() - 3600

        # Mock failed refresh response
        mock_post.return_value = httpx.Response(400, text="Invalid refresh token")

        manager = MDRepoTokenManager(session)
        token = await manager.get_valid_token()

        assert token is None
        # All token keys should be cleared
        assert MDREPO_TOKEN_KEY not in session
        assert MDREPO_REFRESH_TOKEN_KEY not in session
        assert MDREPO_TOKEN_EXPIRES_AT not in session

    async def test_is_token_expired_no_expiration(self, session: SessionMixin) -> None:
        """Test is_token_expired when no expiration info is available."""
        session[MDREPO_TOKEN_KEY] = "test_token"

        manager = MDRepoTokenManager(session)
        # Should return False when no expiration info (can't verify)
        assert manager.is_token_expired() is False

    async def test_is_token_expired_valid(self, session: SessionMixin) -> None:
        """Test is_token_expired with valid token."""
        session[MDREPO_TOKEN_KEY] = "test_token"
        session[MDREPO_TOKEN_EXPIRES_AT] = time.time() + 3600

        manager = MDRepoTokenManager(session)
        assert manager.is_token_expired() is False

    async def test_is_token_expired_expired(self, session: SessionMixin) -> None:
        """Test is_token_expired with expired token."""
        session[MDREPO_TOKEN_KEY] = "test_token"
        session[MDREPO_TOKEN_EXPIRES_AT] = time.time() - 3600

        manager = MDRepoTokenManager(session)
        assert manager.is_token_expired() is True

    async def test_refresh_token_success(self, mock_post: Mock, session: SessionMixin) -> None:
        """Test successful token refresh."""
        session[MDREPO_TOKEN_KEY] = "expired_token"
        session[MDREPO_REFRESH_TOKEN_KEY] = "refresh_token"
        session[MDREPO_TOKEN_EXPIRES_AT] = time.time() - 3600  # Expired

        # Mock successful refresh response
        mock_post.return_value = httpx.Response(
            200, json={"access_token": "new_access_token", "refresh_token": "new_refresh_token", "expires_in": 3600}
        )

        manager = MDRepoTokenManager(session)
        result = await manager.refresh_token()

        assert result is True
        assert session[MDREPO_TOKEN_KEY] == "new_access_token"
        assert session[MDREPO_REFRESH_TOKEN_KEY] == "new_refresh_token"
        assert MDREPO_TOKEN_EXPIRES_AT in session

    async def test_refresh_token_no_refresh_token(self, mock_post: Mock, session: SessionMixin) -> None:
        """Test refresh when no refresh token is available."""
        manager = MDRepoTokenManager(session)
        result = await manager.refresh_token()

        assert result is False
        mock_post.assert_not_called()

    async def test_refresh_token_invalid_refresh_token(self, mock_post: Mock, session: SessionMixin) -> None:
        """Test refresh when refresh token is invalid."""
        session[MDREPO_TOKEN_KEY] = "expired_token"
        session[MDREPO_REFRESH_TOKEN_KEY] = "invalid_refresh_token"
        session[MDREPO_TOKEN_EXPIRES_AT] = time.time() - 3600  # Expired

        # Mock failed refresh response
        mock_post.return_value = httpx.Response(400, text="Invalid refresh token")

        manager = MDRepoTokenManager(session)
        result = await manager.refresh_token()

        assert result is False
        # Tokens should be cleared
        assert MDREPO_TOKEN_KEY not in session
        assert MDREPO_REFRESH_TOKEN_KEY not in session

    async def test_refresh_token_with_retry(
        self, session: SessionMixin, mock_post: Mock, mock_sleep: AsyncMock
    ) -> None:
        """Test refresh with retry on temporary failure."""
        session[MDREPO_TOKEN_KEY] = "expired_token"
        session[MDREPO_REFRESH_TOKEN_KEY] = "refresh_token"
        session[MDREPO_TOKEN_EXPIRES_AT] = time.time() - 3600  # Expired

        # Mock responses: first two fail, third succeeds
        mock_post.side_effect = [
            httpx.Response(500, text="Server error"),
            httpx.Response(500, text="Server error"),
            httpx.Response(
                200, json={"access_token": "new_access_token", "refresh_token": "new_refresh_token", "expires_in": 3600}
            ),
        ]

        manager = MDRepoTokenManager(session)
        result = await manager.refresh_token()

        assert result is True
        assert session[MDREPO_TOKEN_KEY] == "new_access_token"
        assert mock_post.call_count == TOKEN_REFRESH_RETRIES
        # Verify sleep was called twice (between retries)
        assert mock_sleep.call_count == TOKEN_REFRESH_RETRIES - 1
        # Verify exponential backoff: 1s, 2s (for 3 retries)
        expected_delays = [TOKEN_REFRESH_INITIAL_DELAY * (2**i) for i in range(TOKEN_REFRESH_RETRIES - 1)]
        actual_delays = [call[0][0] for call in mock_sleep.call_args_list]
        assert actual_delays == expected_delays

    async def test_refresh_token_all_retries_fail(
        self, session: SessionMixin, mock_post: Mock, mock_sleep: AsyncMock
    ) -> None:
        """Test refresh when all retries fail."""
        session[MDREPO_TOKEN_KEY] = "expired_token"
        session[MDREPO_REFRESH_TOKEN_KEY] = "refresh_token"
        session[MDREPO_TOKEN_EXPIRES_AT] = time.time() - 3600  # Expired

        # Mock failed refresh response
        mock_post.return_value = httpx.Response(500, text="Server error")

        manager = MDRepoTokenManager(session)
        result = await manager.refresh_token()

        assert result is False
        # Should retry 3 times
        assert mock_post.call_count == TOKEN_REFRESH_RETRIES
        # Verify sleep was called twice (between retries)
        assert mock_sleep.call_count == TOKEN_REFRESH_RETRIES - 1
        # Verify exponential backoff: 1s, 2s (for 3 retries)
        expected_delays = [TOKEN_REFRESH_INITIAL_DELAY * (2**i) for i in range(TOKEN_REFRESH_RETRIES - 1)]
        actual_delays = [call[0][0] for call in mock_sleep.call_args_list]
        assert actual_delays == expected_delays

    async def test_refresh_token_no_new_refresh_token(self, mock_post: Mock, session: SessionMixin) -> None:
        """Test refresh when response doesn't include new refresh token."""
        session[MDREPO_TOKEN_KEY] = "expired_token"
        session[MDREPO_REFRESH_TOKEN_KEY] = "refresh_token"
        session[MDREPO_TOKEN_EXPIRES_AT] = time.time() - 3600  # Expired

        # Mock refresh response without new refresh token
        mock_post.return_value = httpx.Response(200, json={"access_token": "new_access_token", "expires_in": 3600})

        manager = MDRepoTokenManager(session)
        result = await manager.refresh_token()

        assert result is True
        assert session[MDREPO_TOKEN_KEY] == "new_access_token"
        # Old refresh token should still be there
        assert session[MDREPO_REFRESH_TOKEN_KEY] == "refresh_token"

    async def test_clear_tokens(self, session: SessionMixin) -> None:
        """Test clearing all tokens."""
        session[MDREPO_TOKEN_KEY] = "test_token"
        session[MDREPO_REFRESH_TOKEN_KEY] = "test_refresh_token"
        session[MDREPO_TOKEN_EXPIRES_AT] = time.time() + 3600

        manager = MDRepoTokenManager(session)
        manager.clear_tokens()

        assert MDREPO_TOKEN_KEY not in session
        assert MDREPO_REFRESH_TOKEN_KEY not in session
        assert MDREPO_TOKEN_EXPIRES_AT not in session

    async def test_has_tokens_true(self, session: SessionMixin) -> None:
        """Test has_tokens when tokens exist."""
        session[MDREPO_TOKEN_KEY] = "test_token"

        manager = MDRepoTokenManager(session)
        assert manager.has_tokens() is True

    async def test_has_tokens_false(self, session: SessionMixin) -> None:
        """Test has_tokens when no tokens exist."""
        manager = MDRepoTokenManager(session)
        assert manager.has_tokens() is False
