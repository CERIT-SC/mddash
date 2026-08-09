import contextlib
import logging
import os
import time
from pathlib import Path

from alembic.runtime.migration import MigrationContext
from alembic.script import ScriptDirectory
from alembic.util.exc import CommandError
from config import DATA_DIR, LOG_FORMAT, LOG_LEVEL
from errors import register_error_handlers
from extensions import db, ma, migrate
from flask import Flask
from flask_migrate import stamp, upgrade
from logging_utils import configure_logging, enable_loggers
from models.simulation import Simulation
from notebook_modules import load_catalog_or_exit
from routes import (
    amber_bp,
    analysis_bp,
    experiments_bp,
    files_bp,
    gmx_bp,
    mdrepo_bp,
    misc_bp,
    notebook_bp,
    notebook_config_bp,
    simulations_bp,
    tuner_bp,
)
from sqlalchemy import inspect as sa_inspect
from utils import start_du_monitor

logger = logging.getLogger(__name__)

MIGRATIONS_DIR = Path(__file__).parent / "migrations"
DU_MONITOR_START_DELAY_SECONDS = 10.0


def _log_duration(phase: str, start: float) -> None:
    with contextlib.suppress(Exception):
        logger.info("startup phase %s completed in %.3fs", phase, time.perf_counter() - start)


def _run_migrations() -> None:
    start = time.perf_counter()
    logger.info("Checking database migrations...")

    script = ScriptDirectory(str(MIGRATIONS_DIR))
    head_rev = script.get_current_head()

    with db.engine.connect() as conn:
        current_rev = MigrationContext.configure(conn).get_current_revision()

    if current_rev is None:
        if sa_inspect(db.engine).get_table_names():
            logger.info("Unversioned DB with tables; stamping to migration baseline...")
            stamp(directory=str(MIGRATIONS_DIR), revision="001", purge=True)
            current_rev = "001"
    else:
        try:
            script.get_revision(current_rev)
        except CommandError:
            logger.error(
                "DB revision '%s' not in migration scripts (head: '%s'). Downgrade the DB first.",
                current_rev,
                head_rev,
            )
            raise RuntimeError(f"DB revision '{current_rev}' is ahead of migration scripts.")

    _log_duration("db-revision-check", start)

    if current_rev == head_rev:
        logger.info("Database is at migration head %s; skipping upgrade", head_rev)
        return

    start = time.perf_counter()
    logger.info("Running database migrations...")
    upgrade(directory=str(MIGRATIONS_DIR))
    _log_duration("migration-upgrade", start)


def _register_blueprints(app: Flask) -> None:
    app.register_blueprint(amber_bp)
    app.register_blueprint(analysis_bp)
    app.register_blueprint(experiments_bp)
    app.register_blueprint(notebook_bp)
    app.register_blueprint(notebook_config_bp)
    app.register_blueprint(tuner_bp)
    app.register_blueprint(gmx_bp)
    app.register_blueprint(simulations_bp)
    app.register_blueprint(files_bp)
    app.register_blueprint(misc_bp)
    app.register_blueprint(mdrepo_bp)


def create_app() -> Flask:
    """
    Create and configure the Flask application.

    Returns:
        Flask: Configured Flask application instance.
    """
    startup_start = time.perf_counter()
    configure_logging(LOG_FORMAT, LOG_LEVEL)
    enable_loggers()
    app = Flask(__name__)

    db_path = DATA_DIR / "experiments.db"
    app.config["SQLALCHEMY_DATABASE_URI"] = f"sqlite:///{db_path}"
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
    app.config["SECRET_KEY"] = os.environ.get("MDREPO_CLIENT_SECRET", "")
    app.config["SESSION_COOKIE_SECURE"] = True
    app.config["SESSION_COOKIE_HTTPONLY"] = True
    app.config["SESSION_COOKIE_SAMESITE"] = "Lax"

    db.init_app(app)
    ma.init_app(app)
    migrate.init_app(app, db, directory=str(MIGRATIONS_DIR))

    reg_start = time.perf_counter()
    _register_blueprints(app)
    register_error_handlers(app)
    _log_duration("route-registration", reg_start)

    # Validate bundled catalog before migrations so a bad catalog fails fast.
    catalog_start = time.perf_counter()
    load_catalog_or_exit()
    _log_duration("notebook-catalog", catalog_start)

    with app.app_context():
        _run_migrations()

    # Names predate per-experiment uniqueness; the wizard can't address
    # duplicate tabs, so reconcile them once per pod start.
    reconcile_start = time.perf_counter()
    Simulation.reconcile_duplicate_names()
    _log_duration("simulation-name-reconciliation", reconcile_start)

    start_du_monitor(DATA_DIR, initial_delay=DU_MONITOR_START_DELAY_SECONDS)
    _log_duration("app-factory", startup_start)

    return app


if __name__ == "__main__":
    logger.info("Starting Flask development server...")
    create_app().run(debug=True, host="0.0.0.0", port=5000)
