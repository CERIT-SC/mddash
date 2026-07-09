"""
Demo profile setup for local development.

Installs all mocks and seeds deterministic test data for UI development.
"""

import contextlib
import logging
import time
from typing import TYPE_CHECKING
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

import responses
from flask import redirect, request, session
from token_manager import MDREPO_TOKEN_EXPIRES_AT, MDREPO_TOKEN_KEY

from .files import ensure_schema_files
from .mocks import install_all_mocks
from .seed import seed_data
from .state import demo_state

if TYPE_CHECKING:
    from flask import Flask
    from werkzeug.wrappers import Response as WerkzeugResponse

logger = logging.getLogger(__name__)

# Global responses mock instance (activated per-request)
_responses_mock: responses.RequestsMock | None = None


def setup_demo_profile(app: "Flask") -> None:
    """
    Install demo mocks and seed deterministic local data.

    This sets up the demo environment with:
    - HTTP response mocking via responses library
    - Kubernetes client mocking via module mutation
    - Tuner trial log mocking via module mutation
    - Deterministic seeded database records
    - Demo MDRepo authentication bypass

    Args:
        app: The Flask application instance.
    """
    global _responses_mock  # noqa: PLW0603

    if demo_state.initialized:
        return

    # Install all mocks (HTTP via responses, K8s via module mutation)
    _responses_mock = install_all_mocks()

    # Install demo MDRepo auth bypass
    _install_demo_mdrepo_auth(app)
    _install_demo_schema_guard(app)

    # Configure session for local development
    app.config["SESSION_COOKIE_SECURE"] = False
    if not app.config.get("SECRET_KEY"):
        app.config["SECRET_KEY"] = "demo-secret"

    # Seed database with test data
    with app.app_context():
        seed_data()

    demo_state.initialized = True
    logger.info("Demo profile initialized with real API routes and mocked integrations.")


def activate_responses() -> None:
    """Activate the responses mock for the current request context."""
    global _responses_mock  # noqa: PLW0602
    if _responses_mock is not None:
        _responses_mock.__enter__()  # noqa: PLC2801


def deactivate_responses() -> None:
    """Deactivate the responses mock after request completion."""
    global _responses_mock  # noqa: PLW0602
    if _responses_mock is not None:
        with contextlib.suppress(Exception):
            _responses_mock.__exit__(None, None, None)


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


def _install_demo_schema_guard(app: "Flask") -> None:
    """Ensure demo schema files exist before writing simulation manifests."""

    @app.before_request
    def _ensure_demo_schema_files() -> None:
        if request.endpoint not in {"simulations.create_simulation_route", "simulations.update_simulation_route"}:
            return
        experiment_id = (request.view_args or {}).get("experiment_id")
        if isinstance(experiment_id, str):
            ensure_schema_files(experiment_id)


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
