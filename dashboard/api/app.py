import logging
import os
from pathlib import Path

from alembic.runtime.migration import MigrationContext
from alembic.script import ScriptDirectory
from alembic.util.exc import CommandError
from config import DATA_DIR, LOG_FORMAT, LOG_LEVEL
from extensions import db, ma, migrate
from flask import Flask
from flask_migrate import stamp, upgrade
from logging_utils import configure_logging, enable_loggers
from routes import (
    analysis_bp,
    experiments_bp,
    files_bp,
    gmx_bp,
    mdrepo_bp,
    misc_bp,
    notebook_bp,
    notebook_config_bp,
    tuner_bp,
)
from sqlalchemy import inspect as sa_inspect
from utils import start_du_monitor

logger = logging.getLogger(__name__)

MIGRATIONS_DIR = Path(__file__).parent / "migrations"


def create_app() -> Flask:
    """
    Create and configure the Flask application.

    Returns:
        Flask: Configured Flask application instance with database, extensions, and blueprints registered.
    """
    app = Flask(__name__)

    # Configuration
    db_path = DATA_DIR / "experiments.db"
    app.config["SQLALCHEMY_DATABASE_URI"] = f"sqlite:///{db_path}"
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

    # Secret key for Flask session (used by MDRepo OAuth)
    app.config["SECRET_KEY"] = os.environ.get("MDREPO_CLIENT_SECRET", "")
    # Secure session cookie settings (recommended for production)
    app.config["SESSION_COOKIE_SECURE"] = True  # Only send over HTTPS
    app.config["SESSION_COOKIE_HTTPONLY"] = True  # Prevent JavaScript access
    app.config["SESSION_COOKIE_SAMESITE"] = "Lax"  # CSRF protection

    # Initialize extensions
    db.init_app(app)
    ma.init_app(app)
    migrate.init_app(app, db, directory=str(MIGRATIONS_DIR))

    app.register_blueprint(analysis_bp)
    app.register_blueprint(experiments_bp)
    app.register_blueprint(notebook_bp)
    app.register_blueprint(notebook_config_bp)
    app.register_blueprint(tuner_bp)
    app.register_blueprint(gmx_bp)
    app.register_blueprint(files_bp)
    app.register_blueprint(misc_bp)
    app.register_blueprint(mdrepo_bp)

    with app.app_context():
        try:
            logger.info("Running database migrations...")
            with db.engine.connect() as conn:
                current_rev = MigrationContext.configure(conn).get_current_revision()
            if current_rev is None:
                # Unversioned DB that already has tables: stamp baseline so upgrade() doesn't
                # try to re-create them (which would fail on existing tables).
                if sa_inspect(db.engine).get_table_names():
                    logger.info("Unversioned DB with tables; stamping to migration baseline...")
                    stamp(directory=str(MIGRATIONS_DIR), revision="001", purge=True)
            else:
                try:
                    ScriptDirectory(str(MIGRATIONS_DIR)).get_revision(current_rev)
                except CommandError:
                    # Revision from old auto-generated migrations that no longer exist
                    logger.info("Unknown DB revision; restamping to migration baseline...")
                    stamp(directory=str(MIGRATIONS_DIR), revision="001", purge=True)
            upgrade(directory=str(MIGRATIONS_DIR))
        except (Exception, SystemExit) as e:
            logger.warning(f"Migration upgrade failed: {e}, falling back to create_all()")
            db.create_all()

    # Alembic may tweak logging handlers; restore our configuration afterwards
    configure_logging(LOG_FORMAT, LOG_LEVEL)
    enable_loggers()

    start_du_monitor(DATA_DIR)

    return app


app = create_app()


# DEVELOPMENT ONLY - when running directly with python app.py
if __name__ == "__main__":
    logger.info("Starting Flask development server...")
    app.run(debug=True, host="0.0.0.0", port=5000)
