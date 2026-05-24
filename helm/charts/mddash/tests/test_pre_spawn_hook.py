"""Tests for MDDash JupyterHub pre-spawn hook helpers."""

import builtins
import importlib.util
from pathlib import Path
from types import SimpleNamespace


def _load_pre_spawn_hook(monkeypatch):
    path = Path(__file__).parents[1] / "files" / "pre_spawn_hook.py"
    monkeypatch.setattr(
        builtins,
        "c",
        SimpleNamespace(KubeSpawner=SimpleNamespace()),
        raising=False,
    )
    spec = importlib.util.spec_from_file_location("pre_spawn_hook_under_test", path)
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_proxy_start_command_waits_for_real_health_endpoints(monkeypatch) -> None:
    """Proxy startup should wait for successful auth and API health checks."""
    module = _load_pre_spawn_hook(monkeypatch)

    command = module._proxy_start_command("/user/alice")

    assert "curl --fail" in command
    assert "http://localhost:5001/health" in command
    assert "http://localhost:5000/user/alice/dash/api/health" in command
    assert "sleep 0.1" in command
    assert "caddy run --config /etc/caddy/Caddyfile --adapter caddyfile" in command
