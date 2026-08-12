"""
Demo profile setup for local development.

Installs all mocks and seeds deterministic test data for UI development.
"""

import logging
import time
from typing import TYPE_CHECKING
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from flask import redirect, request, session
from token_manager import MDREPO_TOKEN_EXPIRES_AT, MDREPO_TOKEN_KEY

from .mocks import install_all_mocks
from .seed import seed_data
from .state import demo_state

if TYPE_CHECKING:
    from flask import Flask
    from werkzeug.wrappers import Response as WerkzeugResponse

logger = logging.getLogger(__name__)


def setup_demo_profile(app: "Flask") -> None:
    """
    Install demo mocks and seed deterministic local data.

    Mocks stay installed process-wide; per-request state is not needed since
    the demo serves a single user.

    Args:
        app: The Flask application instance.
    """
    if demo_state.initialized:
        return

    install_all_mocks()
    _install_demo_mdrepo_auth(app)

    # Configure session for local development
    app.config["SESSION_COOKIE_SECURE"] = False
    if not app.config.get("SECRET_KEY"):
        app.config["SECRET_KEY"] = "demo-secret"

    with app.app_context():
        seed_data()

    demo_state.initialized = True
    logger.info("Demo profile initialized with real API routes and mocked integrations.")


def _install_demo_mdrepo_auth(app: "Flask") -> None:
    """
    Install demo MDRepo OAuth bypass.

    Replaces the initiate_auth endpoint to immediately set a demo token
    and redirect back to the application without requiring actual OAuth.
    """
    endpoint = "mdrepo.initiate_auth"
    if endpoint not in app.view_functions:
        return

    def _demo_mdrepo_auth() -> "WerkzeugResponse":
        """
        Bypass MDRepo OAuth and set demo token directly.

        Returns:
            Redirect response to the return URL.
        """
        return_url = request.args.get("return_url", "/")
        session[MDREPO_TOKEN_KEY] = "demo-access-token"
        session[MDREPO_TOKEN_EXPIRES_AT] = time.time() + 3600
        return redirect(_with_query_param(return_url, "mdrepo_auth", "success"))

    app.view_functions[endpoint] = _demo_mdrepo_auth


def _with_query_param(url: str, key: str, value: str) -> str:
    """
    Add or update a query parameter in a URL.

    Returns:
        URL with the query parameter added or updated.
    """
    parts = urlsplit(url)
    query = dict(parse_qsl(parts.query, keep_blank_values=True))
    query[key] = value
    return urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(query), parts.fragment))
