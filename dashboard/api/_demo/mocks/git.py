"""Offline notebooks-repo clone stubs, installed under MDDASH_DEMO_E2E."""

from pathlib import Path

import anyio


async def _stub_clone(_git_url: str, target_dir: Path, _access_token: "str | None" = None) -> None:
    await anyio.Path(target_dir).mkdir(parents=True, exist_ok=True)


async def _stub_clone_module(
    _git_url: str, _module_path: str, target_dir: Path, _access_token: "str | None" = None
) -> None:
    await anyio.Path(target_dir).mkdir(parents=True, exist_ok=True)


def install_git_mocks() -> None:
    """Replace the git client's clones with offline stubs."""
    from clients.git import GitClient  # ruff:ignore[import-outside-top-level]

    GitClient.clone = lambda _self, *args, **kwargs: _stub_clone(*args, **kwargs)
    GitClient.clone_module = lambda _self, *args, **kwargs: _stub_clone_module(*args, **kwargs)
