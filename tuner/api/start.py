import logging
import os
import sys

import uvicorn
from alembic import command
from alembic.config import Config

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    stream=sys.stdout,
)
logger = logging.getLogger(__name__)

_REQUIRED_ENV = ("TUNER_USER", "TUNER_PASSWORD", "COST_CPU_CORE_HOUR", "COST_GPU_HOUR", "COST_GB_RAM_HOUR")


def validate_config() -> None:
    """Reject startup when required configuration is missing."""
    missing = [v for v in _REQUIRED_ENV if not os.environ.get(v)]
    if missing:
        raise RuntimeError(f"Required environment variables not set: {', '.join(missing)}")


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
