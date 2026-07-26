from pathlib import Path


def test_ray_runtime_workdir_excludes_api_virtual_environment() -> None:
    dockerfile = (Path(__file__).parents[1] / "Dockerfile").read_text(encoding="utf-8")

    assert "COPY --chown=app:app tuner/api/ tuner-runtime/api/" in dockerfile
    assert "RUNTIME_WORKDIR=/app/tuner-runtime" in dockerfile
    assert 'PYTHONPATH="/app/tuner-runtime"' in dockerfile
