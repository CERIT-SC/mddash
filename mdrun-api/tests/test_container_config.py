"""Tests for mdrun-api container runtime configuration."""

from pathlib import Path


def test_uwsgi_suppresses_successful_health_access_logs() -> None:
    """Routine successful /api/health probes should not flood stdout logs."""
    dockerfile = Path(__file__).parents[1] / "Dockerfile"
    content = dockerfile.read_text()

    assert "--route-uri '^/api/health$ donotlog:'" in content
    assert "--log-4xx" in content
    assert "--log-5xx" in content
