"""Offline notebooks-repo clones, used under MDDASH_DEMO_E2E."""

from pathlib import Path

import anyio
from clients.git import GitClient


async def _stub_clone(_git_url: str, target_dir: Path, _access_token: "str | None" = None) -> None:
    await anyio.Path(target_dir).mkdir(parents=True, exist_ok=True)


async def _stub_clone_module(
    _git_url: str, _module_path: str, target_dir: Path, _access_token: "str | None" = None
) -> None:
    await anyio.Path(target_dir).mkdir(parents=True, exist_ok=True)


class OfflineGitClient(GitClient):
    """Git client whose clones only create the target directory (E2E runs offline)."""

    async def clone(self, git_url: str, target_dir: Path, access_token: str | None = None) -> None:
        """Create the target directory."""
        await _stub_clone(git_url, target_dir, access_token)

    async def clone_module(
        self, git_url: str, module_path: str, target_dir: Path, access_token: str | None = None
    ) -> None:
        """Create the target directory."""
        await _stub_clone_module(git_url, module_path, target_dir, access_token)
