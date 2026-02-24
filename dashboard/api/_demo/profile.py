import logging
import time
from typing import TYPE_CHECKING
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from flask import redirect, request, session
from token_manager import MDREPO_TOKEN_EXPIRES_AT, MDREPO_TOKEN_KEY

from .seed import seed_data
from .service_mocks import install_mocks
from .state import demo_state

if TYPE_CHECKING:
    from flask import Flask
    from werkzeug.wrappers import Response as WerkzeugResponse

logger = logging.getLogger(__name__)


def setup_demo_profile(app: "Flask") -> None:
    """Install demo mocks and seed deterministic local data."""
    if demo_state.initialized:
        return

    install_mocks()
    _install_demo_mdrepo_auth(app)

    app.config["SESSION_COOKIE_SECURE"] = False
    if not app.config.get("SECRET_KEY"):
        app.config["SECRET_KEY"] = "demo-secret"

    with app.app_context():
        seed_data()

    demo_state.initialized = True
    logger.info("Demo profile initialized with real API routes and mocked integrations.")


def _install_demo_mdrepo_auth(app: "Flask") -> None:
    endpoint = "mdrepo.initiate_auth"
    if endpoint not in app.view_functions:
        return

    def _demo_mdrepo_auth() -> "WerkzeugResponse":
        return_url = request.args.get("return_url", "/")
        session[MDREPO_TOKEN_KEY] = "demo-access-token"
        session[MDREPO_TOKEN_EXPIRES_AT] = time.time() + 3600
        return redirect(_with_query_param(return_url, "mdrepo_auth", "success"))

    app.view_functions[endpoint] = _demo_mdrepo_auth


def _with_query_param(url: str, key: str, value: str) -> str:
    parts = urlsplit(url)
    query = dict(parse_qsl(parts.query, keep_blank_values=True))
    query[key] = value
    return urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(query), parts.fragment))
