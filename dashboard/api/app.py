import logging
from flask import Flask

from config import DATA_DIR
from extensions import db, ma
from routes import *


logger = logging.getLogger(__name__)


def create_app() -> Flask:
    app = Flask(__name__)
    
    # Configuration
    db_path = DATA_DIR / 'experiments.db'
    app.config['SQLALCHEMY_DATABASE_URI'] = f'sqlite:///{db_path}'
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

    # Initialize extensions
    db.init_app(app)
    ma.init_app(app)

    app.register_blueprint(experiments_bp)
    app.register_blueprint(notebook_bp)
    app.register_blueprint(tuner_bp)
    app.register_blueprint(gmx_bp)
    app.register_blueprint(files_bp)
    app.register_blueprint(misc_bp)

    with app.app_context():
        logger.info("Creating database tables...")
        db.create_all()

    return app


app = create_app()


# DEVELOPMENT ONLY - when running directly with python app.py
if __name__ == '__main__':
    logging.basicConfig(level=logging.DEBUG)
    logger.info("Starting Flask development server...")
    app.run(debug=True, host='0.0.0.0', port=5000)
