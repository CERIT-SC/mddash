"""
Neutralize notebooks-repo git clones for E2E runs (no network, no git).

Installed only under MDDASH_DEMO_E2E; `make demo` keeps real clones.
"""

from pathlib import Path


def _stub_clone(_git_url: str, target_dir: Path, _access_token: "str | None" = None) -> None:
    target_dir.mkdir(parents=True, exist_ok=True)


def _stub_clone_module(_git_url: str, _module_path: str, target_dir: Path, _access_token: "str | None" = None) -> None:
    target_dir.mkdir(parents=True, exist_ok=True)


def install_git_mocks() -> None:
    """Replace the clone functions bound in models.experiment with offline stubs."""
    import models.experiment as experiment_model  # ruff:ignore[import-outside-top-level]

    experiment_model.download_git_repo = _stub_clone  # type: ignore
    experiment_model.download_git_repo_module = _stub_clone_module  # type: ignore
