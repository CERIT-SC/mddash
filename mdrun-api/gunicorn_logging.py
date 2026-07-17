"""Gunicorn logging helpers."""

from datetime import timedelta
from typing import Any

from gunicorn.glogging import Logger

HTTP_SUCCESS_MIN = 200
HTTP_REDIRECT_MIN = 300


class HealthCheckFilter(Logger):
    """Suppress successful health-check access logs."""

    def access(self, resp: Any, req: Any, environ: dict[str, Any], request_time: timedelta) -> None:  # ruff:ignore[any-type]
        """Log non-health requests and failed health probes."""
        status_code = _get_status_code(resp)
        path = environ.get("PATH_INFO", "")
        if path == "/api/health" and status_code is not None and HTTP_SUCCESS_MIN <= status_code < HTTP_REDIRECT_MIN:
            return
        super().access(resp, req, environ, request_time)


def _get_status_code(resp: Any) -> int | None:  # ruff:ignore[any-type]
    status_int = getattr(resp, "status_int", None)
    if isinstance(status_int, int):
        return status_int

    status = getattr(resp, "status", None)
    if isinstance(status, int):
        return status
    if isinstance(status, str):
        code = status.split(maxsplit=1)[0]
        if code.isdigit():
            return int(code)

    return None
