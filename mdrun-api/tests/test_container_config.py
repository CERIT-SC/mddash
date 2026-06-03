"""Tests for mdrun-api container runtime configuration."""

from pathlib import Path


def test_gunicorn_suppresses_successful_health_access_logs() -> None:
    """Routine successful /api/health probes should not flood stdout logs."""
    dockerfile = Path(__file__).parents[1] / "Dockerfile"
    content = dockerfile.read_text()

    assert "gunicorn" in content
    assert "--logger-class gunicorn_logging.HealthCheckFilter" in content
    assert "GUNICORN_WORKERS" in content
    assert "GUNICORN_THREADS" in content
    assert "uwsgi" not in content.lower()
    assert "--route-uri" not in content
