"""Tests for dashboard API container runtime configuration."""

import logging
from pathlib import Path

import pytest
from app import create_app
from logging_utils import HealthCheckFilter


def test_container_serves_the_app_factory_with_uvicorn() -> None:
    dockerfile = (Path(__file__).parents[2] / "Dockerfile").read_text(encoding="utf-8")

    assert '"uvicorn", "app:create_app", "--factory"' in dockerfile
    assert '"--port", "5000"' in dockerfile


def test_app_suppresses_successful_health_access_logs() -> None:
    """Routine successful /health probes should not flood stdout logs."""
    create_app()

    assert any(isinstance(f, HealthCheckFilter) for f in logging.getLogger("uvicorn.access").filters)


@pytest.mark.parametrize(
    ("path", "status", "kept"),
    [
        ("/user/a/dash/api/health", 200, False),
        ("/user/a/dash/api/health?x=1", 200, False),
        ("/user/a/dash/api/health", 503, True),
        ("/user/a/dash/api/experiments", 200, True),
    ],
)
def test_health_filter_drops_only_successful_probes(path: str, status: int, kept: bool) -> None:
    record = logging.LogRecord(
        "uvicorn.access", logging.INFO, "", 0, "%s", ("127.0.0.1", "GET", path, "1.1", status), None
    )
    assert HealthCheckFilter().filter(record) is kept
