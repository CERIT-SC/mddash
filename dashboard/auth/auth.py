import os
import logging
import requests
from flask import Flask, request, jsonify, redirect
from urllib.parse import quote

POD_OWNER = os.environ.get('JUPYTERHUB_USER')
API_TOKEN = os.environ.get('JUPYTERHUB_API_TOKEN')
API_URL = os.environ.get('JUPYTERHUB_API_URL')
HUB_URL = '/hub'

# Fail fast: authentication is critical, don't run without proper config
if not POD_OWNER:
    raise RuntimeError("JUPYTERHUB_USER environment variable is required")
if not API_TOKEN:
    raise RuntimeError("JUPYTERHUB_API_TOKEN environment variable is required")
if not API_URL:
    raise RuntimeError("JUPYTERHUB_API_URL environment variable is required")

app = Flask(__name__)
logger = logging.getLogger(__name__)

# Connection pooling reduces latency on repeated JupyterHub API calls
session = requests.Session()
session.headers.update({'Authorization': f'token {API_TOKEN}'})

@app.route('/auth')
def check_auth():
    """Forward auth endpoint for Caddy. Verifies authenticated user owns this pod."""

    # Caddy forwards original request URI in this header
    original_uri = request.headers.get('X-Forwarded-Uri', request.path)
    login_redirect = redirect(f"{HUB_URL}/login?next={quote(original_uri)}"), 302

    cookie = next((c for name, c in request.cookies.items() if name.startswith('jupyterhub-')), None)
    if not cookie:
        return login_redirect

    try:
        # Ask JupyterHub API: who does this cookie belong to?
        resp = session.get(f"{API_URL}/user", cookies=request.cookies, timeout=5)
        if resp.status_code == 200:
            username = resp.json().get('name')
            if username == POD_OWNER:
                return '', 200

            logger.warning(f"User '{username}' attempted to access pod owned by '{POD_OWNER}'")
            return jsonify({
                'error': 'Forbidden',
                'message': f'You are logged in as "{username}" but this resource belongs to "{POD_OWNER}"'
            }), 403
    except requests.RequestException as e:
        logger.error(f"Failed to verify auth with JupyterHub.", exc_info=True)

    # Cookie invalid/expired, send to login
    return login_redirect

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5001)
