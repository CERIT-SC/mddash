import hashlib
import hmac
import os
import secrets
import time
from http import HTTPStatus

import requests
from flask import Flask, Response, make_response, redirect, request

app = Flask(__name__)


# Environment/config
USER = os.environ.get("JUPYTERHUB_USER", "")
CLIENT_ID = os.environ.get("JUPYTERHUB_CLIENT_ID", "")
API_TOKEN = os.environ.get("JUPYTERHUB_API_TOKEN", "")
API_URL = os.environ.get("JUPYTERHUB_API_URL", "")
CALLBACK_URL = os.environ.get("JUPYTERHUB_OAUTH_CALLBACK_URL", "")
DEFAULT_URL = os.environ.get("JUPYTERHUB_DEFAULT_URL", "/")
SERVICE_PREFIX = os.environ.get("JUPYTERHUB_SERVICE_PREFIX", f"/user/{USER}").rstrip("/")

if not all([USER, CLIENT_ID, API_TOKEN, API_URL, CALLBACK_URL]):
    raise ValueError("Missing one of the required environment variables.")

# Session/cookie config
COOKIE_NAME = "mddash-auth"
STATE_COOKIE = "mddash-state"

# Master secret key for state validation
STATE_SECRET = secrets.token_bytes(32)
HMAC_SHA256_HEX_LENGTH = 64

# {token: (username, expiry_timestamp)}
_sessions: dict[str, tuple[str, float]] = {}
SESSION_LIFETIME = 3600  # 1 hour
_last_cleanup = time.time()
CLEANUP_INTERVAL = 300  # 5 minutes


def remove_expired_sessions() -> None:
    """Remove expired sessions from the in-memory store (throttled)."""
    global _last_cleanup  # noqa: PLW0603
    now = time.time()

    if now - _last_cleanup < CLEANUP_INTERVAL:
        return

    _last_cleanup = now

    expired = [t for t, (_, exp) in _sessions.items() if exp < now]
    for t in expired:
        del _sessions[t]


def is_valid_session(token: str, user: str) -> bool:
    """Check if the session token is valid for the given user."""
    if not token:
        return False
    now = time.time()
    username, expiry = _sessions.get(token, (None, 0))
    return username == user and expiry > now


def create_session(user: str) -> str:
    """Create a new session for the user and return the token."""
    token = secrets.token_urlsafe(32)
    expiry = time.time() + SESSION_LIFETIME
    _sessions[token] = (user, expiry)
    return token


def sign(data: str) -> str:
    """Create HMAC signature for state."""
    return hmac.new(STATE_SECRET, data.encode(), hashlib.sha256).hexdigest()


@app.route("/health")
def health() -> tuple[str, int]:
    """Health check endpoint."""
    return "OK", HTTPStatus.OK


@app.route("/auth")
def auth() -> tuple[str, int] | Response:
    """Authenticate user via session cookie or initiate OAuth flow."""
    remove_expired_sessions()
    token = request.cookies.get(COOKIE_NAME)
    if token and is_valid_session(token, USER):
        return "", HTTPStatus.OK

    # Not authenticated, start OAuth
    state = secrets.token_urlsafe(16)
    signature = sign(state)
    params = {"client_id": CLIENT_ID, "redirect_uri": CALLBACK_URL, "response_type": "code", "state": state}
    url = "/hub/api/oauth2/authorize?" + "&".join(f"{k}={v}" for k, v in params.items())
    resp = make_response(redirect(url))
    resp.set_cookie(STATE_COOKIE, signature, path=SERVICE_PREFIX, httponly=True)
    return resp


@app.route("/oauth_callback")
def oauth_callback() -> tuple[str, int] | Response:
    """Handle OAuth callback, exchange code for token, and create session."""
    code = request.args.get("code")
    state = request.args.get("state")
    signed_state = request.cookies.get(STATE_COOKIE)

    # Verify state by checking HMAC signature
    if not code or not state or not signed_state:
        return "Invalid state", HTTPStatus.BAD_REQUEST
    if not hmac.compare_digest(signed_state, sign(state)):
        return "Invalid state", HTTPStatus.BAD_REQUEST

    # Exchange code for token
    data = {"client_id": CLIENT_ID, "client_secret": API_TOKEN, "grant_type": "authorization_code", "code": code}
    r = requests.post(f"{API_URL}/oauth2/token", data=data, timeout=5)
    if r.status_code != HTTPStatus.OK:
        return "Token exchange failed", HTTPStatus.BAD_REQUEST
    access_token = r.json().get("access_token")
    if not access_token:
        return "No access token", HTTPStatus.BAD_REQUEST

    # Get user info
    headers = {"Authorization": f"token {access_token}"}
    r = requests.get(f"{API_URL}/user", headers=headers, timeout=5)
    if r.status_code != HTTPStatus.OK or r.json().get("name") != USER:
        return "User mismatch", HTTPStatus.FORBIDDEN

    # Create session and set cookie
    token = create_session(USER)
    resp = make_response(redirect(f"{SERVICE_PREFIX}/{DEFAULT_URL.lstrip('/')}"))
    resp.set_cookie(COOKIE_NAME, token, path=SERVICE_PREFIX)
    resp.delete_cookie(STATE_COOKIE, path=SERVICE_PREFIX)
    return resp


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5001)
