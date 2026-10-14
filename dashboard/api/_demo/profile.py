"""
Demo profile setup for local development.

Seeds deterministic data after the real startup migrations and bypasses MDRepo OAuth.
"""

import contextlib
import logging
import time
from collections.abc import AsyncIterator

import anyio
from config import API_PREFIX, DATA_DIR
from fastapi import FastAPI, Request
from fastapi.responses import RedirectResponse
from fastapi.routing import APIRoute
from routes.mdrepo import redirect_with_query
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from token_manager import MDREPO_REFRESH_TOKEN_KEY, MDREPO_TOKEN_EXPIRES_AT, MDREPO_TOKEN_KEY

from .mocks import install_all_mocks
from .seed import seed_data

logger = logging.getLogger(__name__)


def setup_demo_profile(app: FastAPI) -> None:
    """
    Install demo mocks, the MDRepo OAuth bypass, and seeding after startup migrations.

    Mocks stay installed process-wide; per-request state is not needed since
    the demo serves a single user.
    """
    install_all_mocks()
    _install_demo_mdrepo_auth(app)

    startup = app.router.lifespan_context

    @contextlib.asynccontextmanager
    async def seeded_lifespan(application: FastAPI) -> AsyncIterator[None]:
        async with startup(application):
            await anyio.to_thread.run_sync(_seed)
            logger.info("Demo profile initialized with real API routes and mocked integrations.")
            yield

    app.router.lifespan_context = seeded_lifespan


def _seed() -> None:
    engine = create_engine(f"sqlite:///{DATA_DIR / 'experiments.db'}")
    try:
        with Session(engine, expire_on_commit=False) as session:
            seed_data(session)
    finally:
        engine.dispose()


def _install_demo_mdrepo_auth(app: FastAPI) -> None:
    """Route `/mdrepo/auth` to a handler that stores a demo token instead of starting OAuth."""

    async def demo_mdrepo_auth(  # ruff:ignore[unused-async]
        request: Request, return_url: str = "/"
    ) -> RedirectResponse:
        request.session[MDREPO_TOKEN_KEY] = "demo-access-token"
        # The signed cookie outlives the 1h token; the refresh grant lets
        # get_valid_token heal expiry via the mocked token endpoint.
        request.session[MDREPO_REFRESH_TOKEN_KEY] = "demo-refresh-token"
        request.session[MDREPO_TOKEN_EXPIRES_AT] = time.time() + 3600
        return redirect_with_query(return_url, mdrepo_auth="success")

    # Routes match in order: the bypass shadows the real OAuth start.
    app.router.routes.insert(
        0, APIRoute(f"{API_PREFIX}/mdrepo/auth", demo_mdrepo_auth, methods=["GET"], include_in_schema=False)
    )
