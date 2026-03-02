import logging
import os
import shutil

from config import DATA_DIR, LOG_FORMAT, LOG_LEVEL
from extensions import db, ma, migrate
from flask import Flask
from flask_migrate import init, upgrade
from flask_migrate import migrate as flask_migrate
from logging_utils import configure_logging, enable_loggers
from routes import (
    experiments_bp,
    files_bp,
    gmx_bp,
    mdrepo_bp,
    misc_bp,
    notebook_bp,
    tuner_bp,
)
from utils import start_duc_indexer

logger = logging.getLogger(__name__)


def create_app() -> Flask:
    """
    Create and configure the Flask application.

    Returns:
        Flask: Configured Flask application instance with database, extensions, and blueprints registered.
    """
    app = Flask(__name__)

    # Configuration
    db_path = DATA_DIR / "experiments.db"
    migrations_dir = DATA_DIR / "migrations"
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
    migrate.init_app(app, db, directory=str(migrations_dir))

    app.register_blueprint(experiments_bp)
    app.register_blueprint(notebook_bp)
    app.register_blueprint(tuner_bp)
    app.register_blueprint(gmx_bp)
    app.register_blueprint(files_bp)
    app.register_blueprint(misc_bp)
    app.register_blueprint(mdrepo_bp)

    with app.app_context():
        alembic_ini = migrations_dir / "alembic.ini"
        if not alembic_ini.exists():
            logger.info("Initializing database migrations...")
            try:
                # Remove incomplete migrations directory if it exists without alembic.ini
                if migrations_dir.exists():
                    logger.warning("Removing incomplete migrations directory...")
                    shutil.rmtree(migrations_dir)
                init(directory=str(migrations_dir))
                logger.info("Creating initial migration...")
                flask_migrate(message="Initial migration")
            except (Exception, SystemExit) as e:
                logger.error(f"Failed to initialize migrations: {e}")
                logger.info("Creating tables manually as a fallback...")
                db.create_all()
        else:
            # Auto-generate migration if models have changed
            try:
                logger.info("Checking for model changes...")
                flask_migrate(message="Auto-generated migration")
                logger.info("New migration generated")
            except (Exception, SystemExit) as e:
                # Flask-Migrate returns error if no changes, so we log at debug
                logger.debug(f"Migration check finished: {e}")

        try:
            if alembic_ini.exists():
                logger.info("Running database migrations...")
                upgrade(directory=str(migrations_dir))
            else:
                logger.warning("No migrations found, skipping upgrade")
        except (Exception, SystemExit) as e:
            logger.warning(f"Migration upgrade failed: {e}, falling back to create_all()")
            db.create_all()

    # Alembic may tweak logging handlers; restore our configuration afterwards
    configure_logging(LOG_FORMAT, LOG_LEVEL)
    enable_loggers()

    start_duc_indexer(DATA_DIR)

    return app


app = create_app()


# DEVELOPMENT ONLY - when running directly with python app.py
if __name__ == "__main__":
    logger.info("Starting Flask development server...")
    app.run(debug=True, host="0.0.0.0", port=5000)
