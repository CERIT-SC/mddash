import logging
import sys


def configure_logging(log_format: str, level: int | str) -> None:
    """Configure the root logger to behave like `print`."""
    numeric_level = level
    if isinstance(numeric_level, str):
        numeric_level = getattr(logging, numeric_level.upper(), logging.INFO)

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(logging.Formatter(log_format))

    root_logger = logging.getLogger()
    root_logger.handlers = [handler]
    root_logger.setLevel(numeric_level)
    root_logger.disabled = False


def enable_loggers() -> None:
    """Enable all loggers that were disabled by third-party code."""
    logging.getLogger().disabled = False

    for logger_obj in logging.Logger.manager.loggerDict.values():
        if isinstance(logger_obj, logging.Logger):
            logger_obj.disabled = False


class HealthCheckFilter(logging.Filter):
    """
    Suppress successful health-check access logs.

    The uvicorn access logger emits ``(client_addr, method, full_path, http_version, status_code)`` as ``record.args``.
    """

    def filter(self, record: logging.LogRecord) -> bool:
        """Return False to drop successful health probes; keep all else."""
        args = record.args
        if not isinstance(args, tuple) or len(args) < 5:  # ruff:ignore[magic-value-comparison]
            return True
        path = str(args[2]).split("?", 1)[0].rstrip("/")
        return not (path.endswith("/health") and str(args[4]) == "200")
