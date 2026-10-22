"""Tests for mdrun-api environment configuration parsing."""

import json
from typing import Any

import pytest
from config import _json_env


class TestJsonEnv:
    """JSON-encoded env vars fail fast at startup on malformed input."""

    def test_unset_returns_none(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("TEST_JSON", raising=False)
        assert _json_env("TEST_JSON") is None

    def test_empty_string_returns_none(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("TEST_JSON", "")
        assert _json_env("TEST_JSON") is None

    def test_valid_json_is_parsed(self, monkeypatch: pytest.MonkeyPatch) -> None:
        value: dict[str, str] = {"type": "interlink"}
        monkeypatch.setenv("TEST_JSON", json.dumps(value))
        assert _json_env("TEST_JSON") == value

    def test_malformed_json_raises_at_startup(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("TEST_JSON", "{not json")
        with pytest.raises(RuntimeError, match="TEST_JSON must be valid JSON"):
            _json_env("TEST_JSON")


class TestOffloadEnvShape:
    """The offload knobs parse to their pod-spec shapes (dict / list[dict])."""

    def test_node_selector_shape(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("TEST_JSON", '{"nodeType": "virtual-kubelet"}')
        parsed: Any = _json_env("TEST_JSON")
        assert all(isinstance(k, str) and isinstance(v, str) for k, v in parsed.items())

    def test_tolerations_shape(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("TEST_JSON", '[{"key": "virtual-kubelet.io/provider", "operator": "Exists"}]')
        parsed: Any = _json_env("TEST_JSON")
        assert isinstance(parsed, list)
        assert all(isinstance(t, dict) for t in parsed)
