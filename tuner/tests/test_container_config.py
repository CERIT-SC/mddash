from pathlib import Path


def test_ray_runtime_workdir_excludes_api_virtual_environment() -> None:
    dockerfile = (Path(__file__).parents[1] / "Dockerfile").read_text(encoding="utf-8")

    assert "COPY --chown=app:app tuner/api/ tuner-runtime/api/" in dockerfile
    assert "RUNTIME_WORKDIR=/app/tuner-runtime" in dockerfile
    assert 'PYTHONPATH="/app/tuner-runtime"' in dockerfile


def test_uvicorn_suppresses_successful_health_access_logs() -> None:
    """Routine successful /api/health probes should not flood stdout logs."""
    start_py = (Path(__file__).parents[1] / "api" / "start.py").read_text(encoding="utf-8")

    assert "api.access_logging.HealthCheckFilter" in start_py
    assert "log_config=LOGGING_CONFIG" in start_py
