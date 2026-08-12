"""Gunicorn logging helpers."""

from datetime import timedelta

from gunicorn.glogging import Logger


class HealthCheckFilter(Logger):
    """Suppress successful health-check access logs."""

    def access(self, resp: object, req: object, environ: dict[str, str], request_time: timedelta) -> None:
        """Log non-health requests and failed health probes."""
        path = environ.get("PATH_INFO", "").rstrip("/")
        status = str(getattr(resp, "status", "")).partition(" ")[0]
        if path.endswith("/health") and status == "200":
            return
        super().access(resp, req, environ, request_time)
