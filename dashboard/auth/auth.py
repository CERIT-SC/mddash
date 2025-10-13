import os
import time
import secrets
import requests
from flask import Flask, Response, request, redirect, make_response

app = Flask(__name__)


# Environment/config
USER = os.environ.get('JUPYTERHUB_USER')
CLIENT_ID = os.environ.get('JUPYTERHUB_CLIENT_ID')
API_TOKEN = os.environ.get('JUPYTERHUB_API_TOKEN')
API_URL = os.environ.get('JUPYTERHUB_API_URL')
CALLBACK_URL = os.environ.get('JUPYTERHUB_OAUTH_CALLBACK_URL')
DEFAULT_URL = os.environ.get('JUPYTERHUB_DEFAULT_URL', '/')
SERVICE_PREFIX = os.environ.get('JUPYTERHUB_SERVICE_PREFIX', f'/user/{USER}').rstrip('/')

if not all([USER, CLIENT_ID, API_TOKEN, API_URL, CALLBACK_URL]):
    raise ValueError("Missing one of the required environment variables.")

# Session/cookie config
COOKIE_NAME = 'mddash-auth'
STATE_COOKIE = 'mddash-state'


# {token: (username, expiry_timestamp)}
_sessions: dict[str, tuple[str, float]] = {}
SESSION_LIFETIME = 3600  # 1 hour


def remove_expired_sessions() -> None:
    now = time.time()
    expired = [t for t, (_, exp) in _sessions.items() if exp < now]
    for t in expired:
        del _sessions[t]

def is_valid_session(token: str, user: str) -> bool:
    now = time.time()
    username, expiry = _sessions.get(token, (None, 0))
    return username == user and expiry > now

def create_session(user: str) -> str:
    token = secrets.token_urlsafe(32)
    expiry = time.time() + SESSION_LIFETIME
    _sessions[token] = (user, expiry)
    return token


@app.route('/auth')
def auth():
    remove_expired_sessions()
    token = request.cookies.get(COOKIE_NAME)
    if is_valid_session(token, USER):
        return '', 200

    # Not authenticated, start OAuth
    state = secrets.token_urlsafe(16)
    params = {
        'client_id': CLIENT_ID,
        'redirect_uri': CALLBACK_URL,
        'response_type': 'code',
        'state': state
    }
    url = f"/hub/api/oauth2/authorize?" + '&'.join(f"{k}={v}" for k, v in params.items())
    resp = make_response(redirect(url))
    resp.set_cookie(STATE_COOKIE, state, path=SERVICE_PREFIX, httponly=True)
    return resp


@app.route('/oauth_callback')
def oauth_callback():
    code = request.args.get('code')
    state = request.args.get('state')
    if not code or not state or state != request.cookies.get(STATE_COOKIE):
        return 'Invalid state', 400

    # Exchange code for token
    data = {
        'client_id': CLIENT_ID,
        'client_secret': API_TOKEN,
        'grant_type': 'authorization_code',
        'code': code
    }
    r = requests.post(f"{API_URL}/oauth2/token", data=data, timeout=5)
    if r.status_code != 200:
        return 'Token exchange failed', 400
    access_token = r.json().get('access_token')
    if not access_token:
        return 'No access token', 400

    # Get user info
    headers = {'Authorization': f'token {access_token}'}
    r = requests.get(f"{API_URL}/user", headers=headers, timeout=5)
    if r.status_code != 200 or r.json().get('name') != USER:
        return 'User mismatch', 403

    # Create session and set cookie
    token = create_session(USER)
    resp = make_response(redirect(f"{SERVICE_PREFIX}/{DEFAULT_URL.lstrip('/')}"))
    resp.set_cookie(COOKIE_NAME, token, path=SERVICE_PREFIX)
    resp.delete_cookie(STATE_COOKIE, path=SERVICE_PREFIX)
    return resp


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5001)
