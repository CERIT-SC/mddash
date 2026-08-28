"""Tests for config.py environment requirements (import-time, hence subprocess isolation)."""

import os
import subprocess
import sys
from pathlib import Path

API_DIR = Path(__file__).resolve().parents[2]


def _env(**overrides: str | None) -> dict[str, str]:
    env = {key: value for key, value in os.environ.items() if key != "NS_MAX_NOTEBOOKS"}
    for key, value in overrides.items():
        if value is None:
            env.pop(key, None)
        else:
            env[key] = value
    return env


def _import_config(extra_env: dict[str, str]) -> subprocess.CompletedProcess[str]:
    env = _env(**extra_env)
    return subprocess.run(
        [sys.executable, "-c", "import config; print(config.MAX_NOTEBOOKS)"],
        cwd=API_DIR,
        env=env,
        capture_output=True,
        text=True,
        check=False,  # non-zero exit is the asserted outcome
    )


class TestMaxNotebooksRequired:
    """NS_MAX_NOTEBOOKS is quota-critical: the API must fail fast rather than invent a limit."""

    def test_import_fails_loudly_when_missing(self, tmp_path: Path) -> None:
        result = _import_config({"DATA_DIR": str(tmp_path)})

        assert result.returncode != 0
        assert "NS_MAX_NOTEBOOKS" in result.stderr

    def test_import_fails_loudly_when_not_an_int(self, tmp_path: Path) -> None:
        result = _import_config({"DATA_DIR": str(tmp_path), "NS_MAX_NOTEBOOKS": "two"})

        assert result.returncode != 0

    def test_import_succeeds_when_set(self, tmp_path: Path) -> None:
        result = _import_config({"DATA_DIR": str(tmp_path), "NS_MAX_NOTEBOOKS": "3"})

        assert result.returncode == 0
        # config logs its missing-optional-env warnings to stdout before the print.
        assert result.stdout.strip().splitlines()[-1] == "3"
