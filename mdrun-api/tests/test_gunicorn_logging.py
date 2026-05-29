"""Tests for Gunicorn access log filtering."""

from datetime import timedelta
from types import SimpleNamespace

from gunicorn.glogging import Logger
from gunicorn_logging import HealthCheckFilter


def test_successful_health_probe_access_log_is_suppressed(mocker) -> None:  # noqa: ANN001
    """Successful health probes should be filtered using Gunicorn's WSGI environ."""
    mocker.patch.object(Logger, "setup")
    base_access = mocker.patch.object(Logger, "access")
    logger = HealthCheckFilter(cfg=mocker.Mock())
    resp = SimpleNamespace(status="200 OK", headers={})
    req = SimpleNamespace(headers={})
    environ = {"PATH_INFO": "/api/health"}

    logger.access(resp, req, environ, timedelta(milliseconds=1))

    base_access.assert_not_called()


def test_failed_health_probe_access_log_is_preserved(mocker) -> None:  # noqa: ANN001
    """Failed health probes should remain visible in access logs."""
    mocker.patch.object(Logger, "setup")
    base_access = mocker.patch.object(Logger, "access")
    logger = HealthCheckFilter(cfg=mocker.Mock())
    resp = SimpleNamespace(status="500 INTERNAL SERVER ERROR", headers={})
    req = SimpleNamespace(headers={})
    environ = {"PATH_INFO": "/api/health"}
    request_time = timedelta(milliseconds=1)

    logger.access(resp, req, environ, request_time)

    base_access.assert_called_once_with(resp, req, environ, request_time)
