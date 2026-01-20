import os

from config import DB_URL
from extensions import db, ma
from flask import Flask
from flask_cors import CORS
from polling import start_polling
from routes import health_bp, mdrun_bp
from sqlalchemy import text


def create_app() -> Flask:
    """Create and configure the Flask application."""
    app = Flask(__name__)

    app_env = os.getenv("APP_ENV", "prod")
    app.config["ENV"] = app_env
    app.config["DEBUG"] = app_env == "dev"

    app.config["SQLALCHEMY_DATABASE_URI"] = DB_URL
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
    app.config["SQLALCHEMY_ECHO"] = app_env == "dev"

    # Allow SQLite to work across threads
    app.config["SQLALCHEMY_ENGINE_OPTIONS"] = {"connect_args": {"check_same_thread": False}}

    CORS(app)

    db.init_app(app)
    ma.init_app(app)

    app.register_blueprint(mdrun_bp)
    app.register_blueprint(health_bp)

    with app.app_context():
        db.create_all()

        # Enable WAL mode for concurrent reads/writes
        db.session.execute(text("PRAGMA journal_mode=WAL"))
        db.session.commit()

    return app


app = create_app()

# Start job status polling in background thread
start_polling(app)


if __name__ == "__main__":
    debug_mode = os.getenv("APP_ENV", "prod") == "dev"
    app.run(debug=debug_mode, host="0.0.0.0", port=5000)
