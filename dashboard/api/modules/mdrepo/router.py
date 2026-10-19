"""MDRepo OAuth2 authorization code flow for the InvenioRDM repository."""

import logging
import secrets
import time
from http import HTTPStatus
from typing import Annotated, Any
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

import httpx
from clients import mdrepo
from clients.http import client
from core.cache import mdrepo_status_cache
from core.config import (
    API_PREFIX,
    MDREPO_AUTHORIZE_URL,
    MDREPO_CLIENT_ID,
    MDREPO_CLIENT_SECRET,
    MDREPO_REDIRECT_URI,
    MDREPO_SCOPES,
    MDREPO_TOKEN_URL,
    MDREPO_URL,
)
from core.errors import ApiError
from core.responses import problems
from core.schemas import Message
from fastapi import APIRouter, Query, Request
from fastapi.responses import RedirectResponse

from modules.mdrepo.schemas import MDRepoStatus
from modules.mdrepo.tokens import (
    MDREPO_REFRESH_TOKEN_KEY,
    MDREPO_STATE_KEY,
    MDREPO_TOKEN_EXPIRES_AT,
    MDREPO_TOKEN_KEY,
    MDRepoTokenManager,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix=f"{API_PREFIX}/mdrepo", tags=["MDRepo"])

RETURN_URL_KEY = "mdrepo_return_url"

_REDIRECT_RESPONSE: dict[int | str, dict[str, Any]] = {
    HTTPStatus.FOUND: {
        "description": "Redirect",
        "headers": {"Location": {"required": True, "schema": {"type": "string"}}},
    }
}


def redirect_with_query(url: str, **params: str) -> RedirectResponse:
    """Redirect to a URL with query params merged in. The return URL may already carry its own query string."""
    parts = urlsplit(url)
    query = dict(parse_qsl(parts.query, keep_blank_values=True))
    query.update(params)
    return RedirectResponse(
        urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(query), parts.fragment)),
        status_code=HTTPStatus.FOUND,
    )


def _safe_return_url(url: str) -> str:
    r"""Same-origin paths only (open-redirect guard, CWE-601): absolute, protocol-relative, and backslash variants fall back to ``/``."""
    parts = urlsplit(url)
    if parts.scheme or parts.netloc or "\\" in url or not url.startswith("/") or url.startswith("//"):
        return "/"
    return url


@router.get(
    "/status",
    summary="Get MDRepo authentication status",
    operation_id="getMDRepoStatus",
    response_description="Authentication status",
    responses=problems(),
)
async def get_status(request: Request) -> MDRepoStatus:
    """Whether the session holds a token MDRepo accepts."""
    token = request.session.get(MDREPO_TOKEN_KEY)
    if not token:
        return {"authenticated": False}

    try:
        if await mdrepo.is_token_valid(token):
            return {"authenticated": True, "mdrepo_url": MDREPO_URL}
    except httpx.HTTPError as e:
        logger.error(f"MDRepo token validation failed: {e}")
        return {"authenticated": False}

    # Token invalid or expired
    request.session.pop(MDREPO_TOKEN_KEY, None)
    return {"authenticated": False}


@router.get(
    "/auth",
    summary="Begin MDRepo OAuth authorization",
    operation_id="authorizeMDRepo",
    response_class=RedirectResponse,
    status_code=HTTPStatus.FOUND,
    responses={**_REDIRECT_RESPONSE, **problems(503)},
)
async def initiate_auth(request: Request, return_url: str = "/") -> RedirectResponse:
    """
    Redirect to MDRepo's authorization page; `return_url` is where the callback lands afterwards.

    Raises:
        ApiError: 503 if MDRepo OAuth is not configured.
    """
    if not all([MDREPO_CLIENT_ID, MDREPO_CLIENT_SECRET, MDREPO_REDIRECT_URI]):
        raise ApiError(
            HTTPStatus.SERVICE_UNAVAILABLE,
            "MDRepo OAuth is not configured. Contact administrator.",
            "urn:mddash:mdrepo-not-configured",
            "MDRepo integration isn't enabled on this deployment; contact the administrator.",
        )

    # The stored return URL becomes the post-OAuth 302 target.
    state = secrets.token_urlsafe(32)
    request.session[MDREPO_STATE_KEY] = state
    request.session[RETURN_URL_KEY] = _safe_return_url(return_url)

    params = {
        "client_id": MDREPO_CLIENT_ID,
        "redirect_uri": MDREPO_REDIRECT_URI,
        "response_type": "code",
        "state": state,
        "scope": MDREPO_SCOPES,
    }
    logger.info(f"Redirecting to MDRepo OAuth: {MDREPO_AUTHORIZE_URL}")
    return RedirectResponse(f"{MDREPO_AUTHORIZE_URL}?{urlencode(params)}", status_code=HTTPStatus.FOUND)


@router.get(
    "/callback",
    summary="Complete MDRepo OAuth authorization",
    operation_id="completeMDRepoAuthorization",
    response_class=RedirectResponse,
    status_code=HTTPStatus.FOUND,
    responses=_REDIRECT_RESPONSE,
)
async def oauth_callback(
    request: Request,
    code: str | None = None,
    state: str | None = None,
    error: str | None = None,
    error_description: Annotated[str, Query()] = "Authorization denied",
) -> RedirectResponse:
    """Exchange the authorization code for tokens and redirect back with a success or error query parameter."""
    return_url = request.session.pop(RETURN_URL_KEY, "/")
    stored_state = request.session.pop(MDREPO_STATE_KEY, None)

    if error:
        logger.error(f"MDRepo OAuth error: {error} - {error_description}")
        return redirect_with_query(return_url, mdrepo_error=error_description)

    # Validate state to prevent CSRF
    if not state or state != stored_state:
        logger.error("MDRepo OAuth: Invalid state parameter")
        return redirect_with_query(return_url, mdrepo_error="Invalid state parameter")

    if not code:
        logger.error("MDRepo OAuth: No authorization code received")
        return redirect_with_query(return_url, mdrepo_error="No authorization code")

    token_data = {
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": MDREPO_REDIRECT_URI,
        "client_id": MDREPO_CLIENT_ID,
        "client_secret": MDREPO_CLIENT_SECRET,
    }
    try:
        response = await client().post(MDREPO_TOKEN_URL, data=token_data, timeout=30)
    except httpx.HTTPError as e:
        logger.error(f"MDRepo OAuth request error: {e}")
        return redirect_with_query(return_url, mdrepo_error="Request failed")

    if not response.is_success:
        logger.error(f"MDRepo token exchange failed: {response.status_code} - {response.text}")
        return redirect_with_query(return_url, mdrepo_error="Token exchange failed")

    try:
        token_response = response.json()
    except ValueError as e:
        logger.error(f"MDRepo OAuth token response is not JSON: {e}")
        return redirect_with_query(return_url, mdrepo_error="Request failed")
    access_token = token_response.get("access_token")
    refresh_token = token_response.get("refresh_token")
    expires_in = token_response.get("expires_in", 3600)  # Default 1 hour

    if not access_token:
        logger.error("MDRepo OAuth: No access token in response")
        return redirect_with_query(return_url, mdrepo_error="No access token")

    request.session[MDREPO_TOKEN_KEY] = access_token
    if refresh_token:
        request.session[MDREPO_REFRESH_TOKEN_KEY] = refresh_token
        logger.info("MDRepo OAuth: Successfully obtained access and refresh tokens")
    else:
        logger.warning("MDRepo OAuth: No refresh token in response - token refresh will not be available")
    request.session[MDREPO_TOKEN_EXPIRES_AT] = time.time() + expires_in

    # Force a re-sync of publication state with the new token
    mdrepo_status_cache.clear()
    logger.info("MDRepo OAuth: Cleared mdrepo_status_cache")

    return redirect_with_query(return_url, mdrepo_auth="success")


@router.post(
    "/logout",
    summary="Clear MDRepo credentials",
    operation_id="logoutMDRepo",
    response_description="Logout confirmation",
    responses=problems(),
)
async def logout(request: Request) -> Message:
    """Remove all MDRepo tokens from the session."""
    MDRepoTokenManager(request.session).clear_tokens()
    return {"message": "Logged out from MDRepo"}
