"""
MDRepo Token Manager for OAuth2 token management with on-demand refresh.

This module provides a centralized utility for managing MDRepo OAuth2 tokens,
including automatic token refresh when access tokens expire.
"""

import logging
import threading
import time
from http import HTTPStatus
from typing import cast

import requests
from config import MDREPO_CLIENT_ID, MDREPO_CLIENT_SECRET, MDREPO_TOKEN_URL
from flask.sessions import SessionMixin

logger = logging.getLogger(__name__)

# Token refresh configuration constants
TOKEN_REFRESH_RETRIES = 3
TOKEN_REFRESH_RETRY_DELAY = 5  # seconds

# Session keys for MDRepo OAuth (must match routes/mdrepo.py)
MDREPO_TOKEN_KEY = "mdrepo_token"
MDREPO_REFRESH_TOKEN_KEY = "mdrepo_refresh_token"
MDREPO_TOKEN_EXPIRES_AT = "mdrepo_token_expires_at"


class MDRepoTokenManager:
    """
    Manages MDRepo OAuth tokens with on-demand refresh.

    This class provides methods to get valid access tokens, check token expiration,
    and refresh tokens when needed.

    Note:
        This class uses a threading.Lock to prevent concurrent refresh attempts
        within a single token manager instance. However, Flask sessions are not
        thread-safe and should not be accessed from background threads. This class
        should only be used within the Flask request context.
    """

    def __init__(self, session: SessionMixin) -> None:
        """
        Initialize the token manager with a Flask session.

        Args:
            session: Flask session object for storing tokens.

        Warning:
            The session object is not thread-safe and should only be accessed
            within the Flask request context. Do not pass this token manager
            to background threads.
        """
        self.session = session
        self._refresh_lock = threading.Lock()

    def get_valid_token(self) -> str | None:
        """
        Get a valid access token, refreshing if necessary.

        This method checks if the current access token is valid. If it's expired
        or missing, it attempts to refresh using the refresh token.

        Returns:
            Valid access token, or None if unable to obtain a valid token.
        """
        access_token = cast("str | None", self.session.get(MDREPO_TOKEN_KEY))

        # If no access token, try to refresh
        if not access_token:
            logger.warning("No access token found, attempting refresh")
            if self.refresh_token():
                return cast("str | None", self.session.get(MDREPO_TOKEN_KEY))
            return None

        # Check if token is expired
        if self.is_token_expired():
            logger.info("Access token expired, attempting refresh")
            if self.refresh_token():
                return cast("str | None", self.session.get(MDREPO_TOKEN_KEY))
            return None

        # Token is valid
        return access_token

    def is_token_expired(self) -> bool:
        """
        Check if the current access token is expired.

        Returns:
            True if token is expired or missing expiration info, False otherwise.
        """
        expires_at = self.session.get(MDREPO_TOKEN_EXPIRES_AT)

        if not expires_at:
            # If we don't have expiration info, assume token might be valid
            # but we can't verify it
            logger.warning("No token expiration information available")
            return False

        # Check if token has expired
        try:
            expires_at_float = float(expires_at)
        except (ValueError, TypeError):
            logger.warning("Invalid expiration timestamp, assuming expired")
            return True
        return time.time() >= expires_at_float

    def refresh_token(self) -> bool:
        """
        Refresh the access token using the refresh token.

        This method is thread-safe to prevent concurrent refresh attempts.
        It implements retry logic with a fixed delay between attempts.

        Returns:
            True if refresh was successful, False otherwise.
        """
        refresh_token = cast("str | None", self.session.get(MDREPO_REFRESH_TOKEN_KEY))

        if not refresh_token:
            logger.error("No refresh token available, cannot refresh access token")
            return False

        # Use lock to prevent concurrent refresh attempts
        with self._refresh_lock:
            # Check again after acquiring lock in case another thread already refreshed
            if not self.is_token_expired():
                logger.info("Token was refreshed by another thread, using existing token")
                return True

            token_data = {
                "grant_type": "refresh_token",
                "refresh_token": refresh_token,
                "client_id": MDREPO_CLIENT_ID,
                "client_secret": MDREPO_CLIENT_SECRET,
            }

            # Retry logic
            for attempt in range(TOKEN_REFRESH_RETRIES):
                try:
                    logger.info(f"Attempting token refresh (attempt {attempt + 1}/{TOKEN_REFRESH_RETRIES})")
                    response = requests.post(MDREPO_TOKEN_URL, data=token_data, timeout=30)

                    if response.ok:
                        token_response = response.json()
                        new_access_token = token_response.get("access_token")
                        new_refresh_token = token_response.get("refresh_token")
                        expires_in = token_response.get("expires_in", 3600)  # Default 1 hour

                        if not new_access_token:
                            logger.error("Token refresh response missing access_token")
                            return False

                        # Update session with new tokens
                        self.session[MDREPO_TOKEN_KEY] = new_access_token
                        if new_refresh_token:
                            self.session[MDREPO_REFRESH_TOKEN_KEY] = new_refresh_token
                        self.session[MDREPO_TOKEN_EXPIRES_AT] = time.time() + expires_in

                        logger.info("MDRepo token refreshed successfully")
                        return True

                    logger.error(f"Token refresh failed: {response.status_code} - {response.text}")

                    # If refresh token is invalid/expired, clear all tokens
                    if response.status_code == HTTPStatus.BAD_REQUEST:
                        logger.error("Refresh token is invalid or expired, clearing all tokens")
                        self.clear_tokens()
                        return False

                    # Retry on other errors
                    if attempt < TOKEN_REFRESH_RETRIES - 1:
                        time.sleep(TOKEN_REFRESH_RETRY_DELAY)

                except requests.RequestException as e:
                    logger.error(f"Token refresh request failed: {e}")
                    if attempt < TOKEN_REFRESH_RETRIES - 1:
                        time.sleep(TOKEN_REFRESH_RETRY_DELAY)

            # All retries failed
            logger.error("Token refresh failed after all retries")
            return False

    def clear_tokens(self) -> None:
        """
        Clear all stored tokens from the session.

        This is useful when logging out or when tokens become invalid.
        """
        self.session.pop(MDREPO_TOKEN_KEY, None)
        self.session.pop(MDREPO_REFRESH_TOKEN_KEY, None)
        self.session.pop(MDREPO_TOKEN_EXPIRES_AT, None)
        logger.info("All MDRepo tokens cleared from session")

    def has_tokens(self) -> bool:
        """
        Check if any tokens are stored in the session.

        Returns:
            True if access token exists, False otherwise.
        """
        return MDREPO_TOKEN_KEY in self.session
