import logging
import sys

import uvicorn
from alembic import command
from alembic.config import Config

from api.config import TUNER_PASSWORD, TUNER_USER

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    stream=sys.stdout,
)
logger = logging.getLogger(__name__)


def validate_config() -> None:
    """Reject startup when required credentials are missing."""
    if not TUNER_USER or not TUNER_PASSWORD:
        raise RuntimeError("TUNER_USER and TUNER_PASSWORD must be configured")


def main() -> None:
    """Start the FastAPI application."""
    try:
        validate_config()
        command.upgrade(Config("alembic.ini"), "head")
    except Exception:
        logger.exception("Startup validation or database migration failed.")
        sys.exit(1)

    from api.main import app  # ruff: ignore[import-outside-top-level] — intentional: import after migrations complete

    try:
        uvicorn.run(app, host="0.0.0.0", port=8000)
    except Exception:
        logger.exception("Unexpected error while starting.")
        sys.exit(1)


if __name__ == "__main__":
    main()
