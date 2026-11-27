"""Proxy runtime configuration contract tests."""

import ipaddress
import json
import os
import subprocess
from pathlib import Path


def test_admin_api_listens_on_loopback_only() -> None:
    """The admin API rewrites routes without auth, so only in-pod callers may reach it."""
    caddyfile = (Path(__file__).parents[3] / "proxy" / "Caddyfile").read_text(encoding="utf-8")
    global_options = caddyfile.split("\n}", 1)[0]
    admin = next(line.split()[1] for line in global_options.splitlines() if line.split()[:1] == ["admin"])

    assert ipaddress.ip_address(admin.rpartition(":")[0]).is_loopback


def test_runtime_config_is_not_cached() -> None:
    caddyfile = (Path(__file__).parents[3] / "proxy" / "Caddyfile").read_text(encoding="utf-8")
    config_handler = caddyfile.split("handle @config_json {", 1)[1].split("\n\t}", 1)[0]
    assert 'header Cache-Control "no-store"' in config_handler


def test_runtime_config_is_json_encoded(tmp_path: Path) -> None:
    output = tmp_path / "runtime-config.json"
    env = {
        **os.environ,
        "CONFIG_PATH": str(output),
        "CONFIG_ONLY": "1",
        "CADDY_ROUTE_PREFIX": '/user/alice"\\\n',
        "JUPYTERHUB_USER": 'alice";globalThis.pwned=true;//',
        "DEFAULT_NOTEBOOKS_REPO": "https://example.test/notebooks.git",
        "MDPOSIT_URL": "https://mdposit.example.test",
    }
    script = Path(__file__).parents[3] / "proxy" / "entrypoint.sh"

    subprocess.run([str(script)], env=env, check=True)

    config = json.loads(output.read_text(encoding="utf-8"))
    assert config["user"] == env["JUPYTERHUB_USER"]
    assert config["basePath"] == f"{env['CADDY_ROUTE_PREFIX']}/dash"
