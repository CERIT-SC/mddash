import logging
from flask import Flask
from flask_migrate import upgrade, init, migrate as flask_migrate

from config import DATA_DIR, LOG_FORMAT, LOG_LEVEL
from extensions import db, ma, migrate
from routes import *
from logging_utils import configure_logging, enable_loggers


logger = logging.getLogger(__name__)


def create_app() -> Flask:
    app = Flask(__name__)
    
    # Configuration
    db_path = DATA_DIR / 'experiments.db'
    migrations_dir = DATA_DIR / 'migrations'
    app.config['SQLALCHEMY_DATABASE_URI'] = f'sqlite:///{db_path}'
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

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

    with app.app_context():
        if not migrations_dir.exists():
            logger.info("Initializing database migrations...")
            init(directory=str(migrations_dir))
            logger.info("Creating initial migration...")
            flask_migrate(message='Initial migration')
        else:
            # Auto-generate migration if models have changed
            try:
                logger.info("Checking for model changes...")
                flask_migrate(message='Auto-generated migration')
                logger.info("New migration generated")
            except Exception:
                logger.debug("No migration needed", exc_info=True)
        
        try:
            logger.info("Running database migrations...")
            upgrade()
        except Exception:
            logger.warning("Migration failed, creating tables manually", exc_info=True)
            db.create_all()

    # Alembic may tweak logging handlers; restore our configuration afterwards
    configure_logging(LOG_FORMAT, LOG_LEVEL)
    enable_loggers()

    return app


app = create_app()


# DEVELOPMENT ONLY - when running directly with python app.py
if __name__ == '__main__':
    logger.info("Starting Flask development server...")
    app.run(debug=True, host='0.0.0.0', port=5000)
