"""
MDRepo OAuth2 routes for authentication with the InvenioRDM repository.

This module handles the OAuth2 authorization code flow to obtain access tokens
for the MDRepo API.
"""

import logging
import secrets
import time
from http import HTTPStatus
from urllib.parse import urlencode

import requests
from api_response import ApiResponse
from config import (
    API_PREFIX,
    MDREPO_AUTHORIZE_URL,
    MDREPO_CLIENT_ID,
    MDREPO_CLIENT_SECRET,
    MDREPO_REDIRECT_URI,
    MDREPO_SCOPES,
    MDREPO_TOKEN_URL,
    MDREPO_URL,
)
from decorators import handle_exceptions
from flask import Blueprint, Response, redirect, request, session
from token_manager import (
    MDREPO_REFRESH_TOKEN_KEY,
    MDREPO_STATE_KEY,
    MDREPO_TOKEN_EXPIRES_AT,
    MDREPO_TOKEN_KEY,
    MDRepoTokenManager,
)
from werkzeug.wrappers import Response as WerkzeugResponse

logger = logging.getLogger(__name__)

mdrepo_bp = Blueprint("mdrepo", __name__, url_prefix=f"{API_PREFIX}/mdrepo")


def get_mdrepo_token() -> str | None:
    """Get the MDRepo access token from the current session."""
    return session.get(MDREPO_TOKEN_KEY)


@mdrepo_bp.route("/status", methods=["GET"])
@handle_exceptions()
def get_status() -> Response:
    """Check if user has a valid MDRepo token."""
    token = session.get(MDREPO_TOKEN_KEY)

    if not token:
        return ApiResponse.success({"authenticated": False})

    try:
        resp = requests.get(f"{MDREPO_URL}/api/me", headers={"Authorization": f"Bearer {token}"}, timeout=10)

        if resp.status_code == HTTPStatus.OK:
            return ApiResponse.success({"authenticated": True, "mdrepo_url": MDREPO_URL})

        # Token invalid or expired
        session.pop(MDREPO_TOKEN_KEY, None)
        return ApiResponse.success({"authenticated": False})

    except Exception as e:
        logger.error(f"MDRepo token validation failed: {e}")
        return ApiResponse.success({"authenticated": False})


@mdrepo_bp.route("/auth", methods=["GET"])
def initiate_auth() -> Response | WerkzeugResponse:
    """
    Initiate OAuth2 authorization flow with MDRepo.

    Query params:
        return_url: URL to redirect to after successful authentication.
    """
    if not all([MDREPO_CLIENT_ID, MDREPO_CLIENT_SECRET, MDREPO_REDIRECT_URI]):
        return ApiResponse.error(
            "MDRepo OAuth is not configured. Contact administrator.", HTTPStatus.SERVICE_UNAVAILABLE
        )

    # Store return URL and state in session
    return_url = request.args.get("return_url", "/")
    state = secrets.token_urlsafe(32)
    session[MDREPO_STATE_KEY] = state
    session["mdrepo_return_url"] = return_url

    # Build authorization URL
    params = {
        "client_id": MDREPO_CLIENT_ID,
        "redirect_uri": MDREPO_REDIRECT_URI,
        "response_type": "code",
        "state": state,
        "scope": MDREPO_SCOPES,
    }

    auth_url = f"{MDREPO_AUTHORIZE_URL}?{urlencode(params)}"
    logger.info(f"Redirecting to MDRepo OAuth: {MDREPO_AUTHORIZE_URL}")

    return redirect(auth_url)


@mdrepo_bp.route("/callback", methods=["GET"])
def oauth_callback() -> WerkzeugResponse:
    """Handle OAuth2 callback from MDRepo."""
    code = request.args.get("code")
    state = request.args.get("state")
    error = request.args.get("error")

    return_url = session.pop("mdrepo_return_url", "/")
    stored_state = session.pop(MDREPO_STATE_KEY, None)

    # Check for OAuth errors
    if error:
        error_description = request.args.get("error_description", "Authorization denied")
        logger.error(f"MDRepo OAuth error: {error} - {error_description}")
        return redirect(f"{return_url}?mdrepo_error={error_description}")

    # Validate state to prevent CSRF
    if not state or state != stored_state:
        logger.error("MDRepo OAuth: Invalid state parameter")
        return redirect(f"{return_url}?mdrepo_error=Invalid+state+parameter")

    if not code:
        logger.error("MDRepo OAuth: No authorization code received")
        return redirect(f"{return_url}?mdrepo_error=No+authorization+code")

    # Exchange code for token
    try:
        token_data = {
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": MDREPO_REDIRECT_URI,
            "client_id": MDREPO_CLIENT_ID,
            "client_secret": MDREPO_CLIENT_SECRET,
        }

        response = requests.post(MDREPO_TOKEN_URL, data=token_data, timeout=30)

        if not response.ok:
            logger.error(f"MDRepo token exchange failed: {response.status_code} - {response.text}")
            return redirect(f"{return_url}?mdrepo_error=Token+exchange+failed")

        token_response = response.json()
        access_token = token_response.get("access_token")
        refresh_token = token_response.get("refresh_token")
        expires_in = token_response.get("expires_in", 3600)  # Default 1 hour

        if not access_token:
            logger.error("MDRepo OAuth: No access token in response")
            return redirect(f"{return_url}?mdrepo_error=No+access+token")

        # Store complete token information in session
        session[MDREPO_TOKEN_KEY] = access_token
        if refresh_token:
            session[MDREPO_REFRESH_TOKEN_KEY] = refresh_token
            logger.info("MDRepo OAuth: Successfully obtained access and refresh tokens")
        else:
            logger.warning("MDRepo OAuth: No refresh token in response - token refresh will not be available")
        session[MDREPO_TOKEN_EXPIRES_AT] = time.time() + expires_in

        return redirect(f"{return_url}?mdrepo_auth=success")

    except requests.RequestException as e:
        logger.error(f"MDRepo OAuth request error: {e}")
        return redirect(f"{return_url}?mdrepo_error=Request+failed")


@mdrepo_bp.route("/logout", methods=["POST"])
@handle_exceptions()
def logout() -> Response:
    """Remove all MDRepo tokens from session."""
    token_manager = MDRepoTokenManager(session)
    token_manager.clear_tokens()
    return ApiResponse.success({"message": "Logged out from MDRepo"})
