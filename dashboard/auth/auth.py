import hashlib
import hmac
import logging
import os
import secrets
import threading
import time
from http import HTTPStatus

import requests
from flask import Flask, Response, make_response, redirect, request

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 4096

logger = logging.getLogger(__name__)
_first_health_logged = False


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

logger.info("auth app initialized for user %s", USER)

# Session/cookie config
COOKIE_NAME = "mddash-auth"
STATE_COOKIE = "mddash-state"

# Master secret key for state validation
STATE_SECRET = secrets.token_bytes(32)
HMAC_SHA256_HEX_LENGTH = 64

# {token: (username, expiry_timestamp)}
_sessions: dict[str, tuple[str, float]] = {}
_login_tokens: dict[str, tuple[str, float]] = {}
_token_store_lock = threading.Lock()
SESSION_LIFETIME = 3600  # 1 hour
_last_cleanup = time.time()
CLEANUP_INTERVAL = 300  # 5 minutes

LOGIN_TOKEN_PAGE = """<!doctype html>
<html lang="en">
<head><meta charset="utf-8"><meta name="viewport" content="width=device-width"><title>MDDash login</title></head>
<body><p id="status">Signing in...</p><script>
const status = document.getElementById("status");
const token = new URLSearchParams(window.location.hash.slice(1)).get("token");
window.history.replaceState(null, "", window.location.pathname);
if (!token) {
  status.textContent = "Invalid login link.";
} else {
  fetch(window.location.pathname, {
    method: "POST",
    headers: {"Content-Type": "application/json"},
    body: JSON.stringify({token})
  }).then(async response => {
    const result = await response.json();
    if (!response.ok) throw new Error(result.error || "Login failed.");
    window.location.replace(result.redirect_url);
  }).catch(error => { status.textContent = error.message; });
}
</script></body>
</html>"""


def remove_expired_sessions() -> None:
    """Remove expired sessions from the in-memory store (throttled)."""
    global _last_cleanup  # ruff:ignore[global-statement]
    now = time.time()

    if now - _last_cleanup < CLEANUP_INTERVAL:
        return

    _last_cleanup = now

    with _token_store_lock:
        expired = [t for t, (_, exp) in _sessions.items() if exp < now]
        for t in expired:
            del _sessions[t]
        expired_login_tokens = [t for t, (_, exp) in _login_tokens.items() if exp < now]
        for t in expired_login_tokens:
            del _login_tokens[t]


def is_valid_session(token: str, user: str) -> bool:
    """
    Check if the session token is valid for the given user.

    Returns:
        bool: True if the token exists, belongs to the user, and has not expired.
    """
    if not token:
        return False
    now = time.time()
    with _token_store_lock:
        username, expiry = _sessions.get(token, (None, 0))
    return username == user and expiry > now


def create_session(user: str) -> str:
    """
    Create a new session for the user and return the token.

    Returns:
        str: A URL-safe random session token.
    """
    token = secrets.token_urlsafe(32)
    expiry = time.time() + SESSION_LIFETIME
    with _token_store_lock:
        _sessions[token] = (user, expiry)
    return token


def create_login_token_value(user: str) -> str:
    """
    Create a one-time credential kept separate from browser sessions.

    Returns:
        str: A URL-safe random login token.
    """
    token = secrets.token_urlsafe(32)
    expiry = time.time() + SESSION_LIFETIME
    with _token_store_lock:
        _login_tokens[token] = (user, expiry)
    return token


def consume_login_token(token: str, user: str) -> bool:
    """
    Atomically remove and validate a one-time login token.

    Returns:
        bool: True if the token existed, belonged to the user, and had not expired.
    """
    with _token_store_lock:
        session = _login_tokens.pop(token, None)
    if session is None:
        return False
    username, expiry = session
    return username == user and expiry > time.time()


def sign(data: str) -> str:
    """
    Create HMAC signature for state.

    Returns:
        str: Hex-encoded HMAC-SHA256 digest of the input data.
    """
    return hmac.new(STATE_SECRET, data.encode(), hashlib.sha256).hexdigest()


@app.route("/health")
def health() -> tuple[str, int]:
    """
    Health check endpoint.

    Returns:
        tuple[str, int]: A plain-text OK body and a 200 status code.
    """
    global _first_health_logged  # ruff:ignore[global-statement]
    if not _first_health_logged:
        logger.info("auth first health response served")
        _first_health_logged = True
    return "OK", HTTPStatus.OK


@app.route("/auth")
def auth() -> tuple[str, int] | Response:
    """
    Authenticate user via session cookie or initiate OAuth flow.

    Returns:
        tuple[str, int] | Response: Empty 200 if already authenticated, or a
        redirect response to the OAuth authorization URL.
    """
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
    """
    Handle OAuth callback, exchange code for token, and create session.

    Returns:
        tuple[str, int] | Response: A redirect to the default URL on success, or
        an error tuple with a 400/403 status code on failure.
    """
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


@app.route("/create-login-token", methods=["POST"])
def create_login_token() -> tuple[dict, int]:
    """
    Generate a one-time use login token for passwordless access.

    This endpoint must be called from an already authenticated session.
    It creates a new session token and returns a shareable login URL.

    Returns:
        JSON response with 'login_url' and 'expires_in' fields.
    """
    # Check that caller has a valid session (already authenticated)
    auth_token = request.cookies.get(COOKIE_NAME)
    if not auth_token or not is_valid_session(auth_token, USER):
        return {"error": "Authentication required"}, HTTPStatus.UNAUTHORIZED

    # Create a new session token for passwordless access
    login_token_val = create_login_token_value(USER)

    # Construct the one-time login URL
    login_url = f"{SERVICE_PREFIX}/dash/auth/login-token#token={login_token_val}"

    logger.info("Passwordless login token created for user %s", USER)

    return {"login_url": login_url, "expires_in": SESSION_LIFETIME}, HTTPStatus.OK


@app.route("/login-token", methods=["GET", "POST"])
def login_token_endpoint() -> Response:
    """
    Serve the login page or consume a one-time token from a POST body.

    The GET response reads the token from the URL fragment in the browser and
    submits it as JSON to POST, keeping it out of request URLs and referrers.

    Returns:
        Login page for GET, or JSON with a redirect target for POST.
    """
    if request.method == "GET":
        resp = make_response(LOGIN_TOKEN_PAGE, HTTPStatus.OK)
        resp.headers["Content-Type"] = "text/html; charset=utf-8"
        resp.headers["Cache-Control"] = "no-store"
        resp.headers["Referrer-Policy"] = "no-referrer"
        return resp

    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        return make_response({"error": "Invalid JSON payload"}, HTTPStatus.BAD_REQUEST)
    token = payload.get("token")

    if not isinstance(token, str) or not token:
        return make_response({"error": "Missing token"}, HTTPStatus.BAD_REQUEST)

    if not consume_login_token(token, USER):
        logger.warning("Invalid or expired login token attempted for user %s", USER)
        return make_response({"error": "Invalid or expired token"}, HTTPStatus.UNAUTHORIZED)

    # Create a fresh session for the browser
    new_token = create_session(USER)

    resp = make_response({"redirect_url": f"{SERVICE_PREFIX}/dash/"}, HTTPStatus.OK)
    resp.set_cookie(COOKIE_NAME, new_token, path=SERVICE_PREFIX, secure=True, httponly=True, samesite="Lax")

    logger.info("Passwordless login successful for user %s", USER)
    return resp


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5001)
