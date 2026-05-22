import importlib
import os
from collections.abc import Callable
from typing import cast

from config import DB_URL
from extensions import db, ma
from flask import Flask
from flask_cors import CORS
from polling import start_polling
from routes import amber_bp, gmx_bp, health_bp
from sqlalchemy import text

PostForkHook = Callable[[Callable[[], None]], Callable[[], None]]


def _load_uwsgi_postfork() -> PostForkHook | None:
    try:
        uwsgidecorators = importlib.import_module("uwsgidecorators")
    except ImportError:
        return None

    return cast("PostForkHook", uwsgidecorators.postfork)


def create_app() -> Flask:
    """
    Create and configure the Flask application.

    Returns:
        Flask: The configured Flask application instance.
    """
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

    app.register_blueprint(gmx_bp)
    app.register_blueprint(amber_bp)
    app.register_blueprint(health_bp)

    with app.app_context():
        db.create_all()

        # Enable WAL mode for concurrent reads/writes
        db.session.execute(text("PRAGMA journal_mode=WAL"))
        db.session.commit()

    return app


def register_polling_startup(app: Flask, postfork: PostForkHook | None = None) -> None:
    """
    Register job polling after uWSGI forks worker processes.

    Starting threads before uWSGI forks can leave workers unable to serve HTTP
    requests. Outside uWSGI, start polling immediately for local/dev runs.
    """
    hook = postfork or _load_uwsgi_postfork()

    if hook is None:
        start_polling(app)
        return

    @hook
    def _start_polling_after_fork() -> None:
        start_polling(app)


app = create_app()

register_polling_startup(app)


if __name__ == "__main__":
    debug_mode = os.getenv("APP_ENV", "prod") == "dev"
    app.run(debug=debug_mode, host="0.0.0.0", port=5000)
