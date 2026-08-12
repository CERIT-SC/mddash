"""Tests for dashboard API container runtime configuration."""

from pathlib import Path


def test_gunicorn_suppresses_successful_health_access_logs() -> None:
    """Routine successful /health probes should not flood stdout logs."""
    dockerfile = Path(__file__).parents[2] / "Dockerfile"
    content = dockerfile.read_text(encoding="utf-8")

    assert "--logger-class" in content
    assert "gunicorn_logging.HealthCheckFilter" in content
