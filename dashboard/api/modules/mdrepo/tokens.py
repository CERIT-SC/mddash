"""MDRepo OAuth2 token management with on-demand refresh; tokens live in the signed session cookie."""

import asyncio
import logging
import time
from collections.abc import MutableMapping
from dataclasses import dataclass
from http import HTTPStatus
from typing import TYPE_CHECKING, Any, cast

import httpx
from core.cache import mdrepo_status_cache
from core.config import MDREPO_CLIENT_ID, MDREPO_CLIENT_SECRET

if TYPE_CHECKING:
    from clients.mdrepo import MDRepoClient

logger = logging.getLogger(__name__)

TOKEN_REFRESH_RETRIES = 3
TOKEN_REFRESH_INITIAL_DELAY = 1  # seconds (exponential backoff: 1s, 2s, 4s)
TOKEN_EXPIRATION_BUFFER = 60  # seconds

# Session keys for MDRepo OAuth
MDREPO_TOKEN_KEY = "mdrepo_token"
MDREPO_STATE_KEY = "mdrepo_oauth_state"
MDREPO_REFRESH_TOKEN_KEY = "mdrepo_refresh_token"
MDREPO_TOKEN_EXPIRES_AT = "mdrepo_token_expires_at"


@dataclass(frozen=True)
class MDRepoCredentials:
    """Session tokens handed to the durable upload worker."""

    access_token: str
    refresh_token: str
    expires_at: str


# Serializes refreshes: concurrent requests would otherwise each spend the single-use refresh token.
_refresh_lock = asyncio.Lock()


class MDRepoTokenManager:
    """Valid MDRepo access tokens from the session, refreshing expired ones."""

    def __init__(self, session: MutableMapping[str, Any], mdrepo: "MDRepoClient") -> None:
        """Bind to a request session mapping and the MDRepo client that refreshes its tokens."""
        self.session = session
        self._mdrepo = mdrepo

    async def get_valid_token(self) -> str | None:
        """Return the access token, refreshed when missing or expired; None when no valid token is obtainable."""
        access_token = cast("str | None", self.session.get(MDREPO_TOKEN_KEY))

        if not access_token:
            logger.warning("No access token found, attempting refresh")
        elif self.is_token_expired():
            logger.info("Access token expired, attempting refresh")
        else:
            return access_token

        if await self.refresh_token():
            return cast("str | None", self.session.get(MDREPO_TOKEN_KEY))
        return None

    async def get_credentials(self) -> MDRepoCredentials | None:
        """Return a valid access token plus the refresh grant, or None when unauthenticated."""
        access_token = await self.get_valid_token()
        if not access_token:
            return None
        return MDRepoCredentials(
            access_token=access_token,
            refresh_token=str(self.session.get(MDREPO_REFRESH_TOKEN_KEY, "")),
            expires_at=str(self.session.get(MDREPO_TOKEN_EXPIRES_AT, 0)),
        )

    def is_token_expired(self) -> bool:
        """Whether the access token is expired; unknown expiry counts as valid, invalid expiry as expired."""
        expires_at = self.session.get(MDREPO_TOKEN_EXPIRES_AT)
        if not expires_at:
            logger.warning("No token expiration information available")
            return False

        try:
            expires_at_float = float(expires_at)
        except (ValueError, TypeError):
            logger.warning("Invalid expiration timestamp, assuming expired")
            return True
        return time.time() >= expires_at_float - TOKEN_EXPIRATION_BUFFER

    async def refresh_token(self) -> bool:
        """Refresh the access token with the refresh token (retries with exponential backoff)."""
        refresh_token = cast("str | None", self.session.get(MDREPO_REFRESH_TOKEN_KEY))
        if not refresh_token:
            logger.error("No refresh token available, cannot refresh access token")
            return False

        async with _refresh_lock:
            # Another request may have refreshed while this one waited for the lock.
            if self.session.get(MDREPO_TOKEN_KEY) and not self.is_token_expired():
                logger.info("Token was refreshed concurrently, using existing token")
                return True

            token_data = {
                "grant_type": "refresh_token",
                "refresh_token": refresh_token,
                "client_id": MDREPO_CLIENT_ID,
                "client_secret": MDREPO_CLIENT_SECRET,
            }
            for attempt in range(TOKEN_REFRESH_RETRIES):
                try:
                    logger.info(f"Attempting token refresh (attempt {attempt + 1}/{TOKEN_REFRESH_RETRIES})")
                    response = await self._mdrepo.request_token(token_data)
                    if response.is_success:
                        return self._store_refreshed(response.json())

                    logger.error(f"Token refresh failed: {response.status_code} - {response.text}")
                    if response.status_code == HTTPStatus.BAD_REQUEST:
                        logger.error("Refresh token is invalid or expired, clearing all tokens")
                        self.clear_tokens()
                        return False
                except httpx.HTTPError as e:
                    logger.error(f"Token refresh request failed: {e}")

                if attempt < TOKEN_REFRESH_RETRIES - 1:
                    await asyncio.sleep(TOKEN_REFRESH_INITIAL_DELAY * (2**attempt))

            logger.error("Token refresh failed after all retries")
            return False

    def _store_refreshed(self, token_response: dict) -> bool:
        new_access_token = token_response.get("access_token")
        if not new_access_token:
            logger.error("Token refresh response missing access_token")
            return False

        self.session[MDREPO_TOKEN_KEY] = new_access_token
        if "refresh_token" in token_response:
            if new_refresh_token := token_response.get("refresh_token"):
                self.session[MDREPO_REFRESH_TOKEN_KEY] = new_refresh_token
            else:
                logger.warning(
                    "Token refresh response explicitly cleared refresh_token; removing stored refresh token from session"
                )
                self.session.pop(MDREPO_REFRESH_TOKEN_KEY, None)
        self.session[MDREPO_TOKEN_EXPIRES_AT] = time.time() + token_response.get("expires_in", 3600)

        mdrepo_status_cache.clear()
        logger.info("MDRepo token refreshed successfully, cleared mdrepo_status_cache")
        return True

    def clear_tokens(self) -> None:
        """Clear all stored tokens from the session (logout or invalid tokens)."""
        self.session.pop(MDREPO_TOKEN_KEY, None)
        self.session.pop(MDREPO_REFRESH_TOKEN_KEY, None)
        self.session.pop(MDREPO_TOKEN_EXPIRES_AT, None)
        mdrepo_status_cache.clear()
        logger.info("All MDRepo tokens cleared from session, cleared mdrepo_status_cache")

    def has_session(self) -> bool:
        """Whether the user authenticated with MDRepo at some point (an access or refresh token is stored)."""
        return bool(self.session.get(MDREPO_TOKEN_KEY) or self.session.get(MDREPO_REFRESH_TOKEN_KEY))

    def has_tokens(self) -> bool:
        """Whether an access token is stored."""
        return MDREPO_TOKEN_KEY in self.session
