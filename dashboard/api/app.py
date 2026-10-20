import asyncio
import contextlib
import logging
import secrets
import time
from collections.abc import AsyncIterator

import anyio
from clients import Clients
from core.config import API_PREFIX, DATA_DIR, LOG_FORMAT, LOG_LEVEL, MDREPO_CLIENT_SECRET
from core.db import dispose_engine, init_engine, run_migrations
from core.errors import register_exception_handlers
from core.logging_utils import HealthCheckFilter, configure_logging, enable_loggers
from core.utils import du_monitor
from fastapi import FastAPI
from modules.archive import router as archive
from modules.experiments import router as experiments
from modules.files import router as files
from modules.jobs.amber import router as amber
from modules.jobs.analysis import router as analysis
from modules.jobs.gmx import router as gmx
from modules.jobs.tuner import router as tuner
from modules.mdrepo import router as mdrepo
from modules.notebooks import router as notebooks
from modules.notebooks.catalog import load_catalog_or_exit
from modules.publishing import router as publishing
from modules.simulations import router as simulations
from modules.system import router as system
from openapi import install_openapi
from starlette.middleware.sessions import SessionMiddleware

logger = logging.getLogger(__name__)

DU_MONITOR_START_DELAY_SECONDS = 10.0
DB_PATH_NAME = "experiments.db"

# Inclusion order is the path order of the generated OpenAPI document.
ROUTERS = (system, experiments, publishing, archive, mdrepo, files, simulations, gmx, amber, tuner, notebooks, analysis)


@contextlib.asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Validate the catalog, migrate the database, and run the du monitor for the app's lifetime."""
    start = time.perf_counter()
    du_task: asyncio.Task | None = None
    try:
        # Validate bundled catalog before migrations so a bad catalog fails fast.
        load_catalog_or_exit()
        db_path = DATA_DIR / DB_PATH_NAME
        await anyio.to_thread.run_sync(run_migrations, db_path)
        init_engine(db_path)
        du_task = asyncio.create_task(du_monitor(DATA_DIR, initial_delay=DU_MONITOR_START_DELAY_SECONDS))
        logger.info("startup completed in %.3fs", time.perf_counter() - start)
        yield
    finally:
        if du_task is not None:
            du_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await du_task
        try:
            await app.state.clients.aclose()
        finally:
            await dispose_engine()


def create_app(
    *, clients: Clients | None = None, secure_cookies: bool = True, session_secret: str | None = None
) -> FastAPI:
    """
    Build the FastAPI application (startup work runs in the lifespan, not at import).

    Args:
        clients: Upstream clients (tests and the demo pass fakes); production clients by default.
        secure_cookies: Mark the session cookie Secure (the local demo serves plain http).
        session_secret: Session signing key; defaults to the MDRepo client secret.
    """
    configure_logging(LOG_FORMAT, LOG_LEVEL)
    enable_loggers()
    # uvicorn configures its loggers before calling the factory.
    access_logger = logging.getLogger("uvicorn.access")
    if not any(isinstance(f, HealthCheckFilter) for f in access_logger.filters):
        access_logger.addFilter(HealthCheckFilter())
    app = FastAPI(
        title="MDDash Dashboard API",
        version="1.0.0",
        description="API for experiment, simulation, compute, analysis, notebook, file, and publication workflows.",
        lifespan=lifespan,
        openapi_url=f"{API_PREFIX}/openapi.json",
        docs_url=f"{API_PREFIX}/docs",
        redoc_url=None,
        separate_input_output_schemas=False,
    )
    app.state.clients = clients or Clients.create()
    # MDRepo OAuth tokens live in this signed cookie; without a configured secret
    # (MDRepo disabled) sessions only need to survive this process.
    app.add_middleware(
        SessionMiddleware,
        secret_key=session_secret or MDREPO_CLIENT_SECRET or secrets.token_hex(32),
        https_only=secure_cookies,
        same_site="lax",
        max_age=None,
    )
    register_exception_handlers(app)
    for module in ROUTERS:
        app.include_router(module.router)
    install_openapi(app)
    return app
