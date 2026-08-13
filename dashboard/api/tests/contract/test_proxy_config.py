"""Proxy runtime configuration contract tests."""

from pathlib import Path


def test_runtime_config_is_not_cached() -> None:
    caddyfile = (Path(__file__).parents[3] / "proxy" / "Caddyfile").read_text(encoding="utf-8")
    config_handler = caddyfile.split("handle @config_js {", 1)[1].split("\n\t}", 1)[0]
    assert 'header Cache-Control "no-store"' in config_handler


def test_runtime_config_exposes_hub_navigation_routes() -> None:
    caddyfile = (Path(__file__).parents[3] / "proxy" / "Caddyfile").read_text(encoding="utf-8")
    config_handler = caddyfile.split("handle @config_js {", 1)[1].split("\n\t}", 1)[0]
    assert 'hubHomeUrl: "/hub/home"' in config_handler
    assert 'hubTokenUrl: "/hub/token"' in config_handler
    assert 'logoutUrl: "/hub/logout"' in config_handler
