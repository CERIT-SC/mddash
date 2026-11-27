"""Tests for auth container runtime configuration."""

import json
from pathlib import Path

from gunicorn.config import Config
from gunicorn.util import parse_address

DOCKERFILE = Path(__file__).parents[1] / "Dockerfile"


def _container_command() -> list[str]:
    lines = DOCKERFILE.read_text(encoding="utf-8").splitlines()
    cmd = next(line for line in reversed(lines) if line.startswith("CMD "))  # the last CMD wins
    return json.loads(cmd.removeprefix("CMD "))


def test_gunicorn_suppresses_successful_health_access_logs() -> None:
    """Routine successful /health probes should not fill stdout logs."""
    content = DOCKERFILE.read_text(encoding="utf-8")

    assert "--logger-class" in content
    assert "gunicorn_logging.HealthCheckFilter" in content


def test_gunicorn_listens_on_loopback_only() -> None:
    """Only the in-pod proxy calls auth, so it must not face the pod network."""
    command = _container_command()

    binds = Config().parser().parse_args(command[1:]).bind

    assert [parse_address(bind) for bind in binds] == [("127.0.0.1", 5001)]
