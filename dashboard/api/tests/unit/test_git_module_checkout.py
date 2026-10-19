"""Unit tests for selective git checkout of curated notebook modules."""

import asyncio
import subprocess
from collections.abc import Callable
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest
from core.errors import InternalServerError, NotFound
from core.utils import download_git_repo_module

_real_exec = asyncio.create_subprocess_exec


def _make_real_repo(repo_dir: Path, module_path: str, other_path: str) -> None:
    """Create a real local git repo with two module directories."""
    repo_dir.mkdir(parents=True)
    (repo_dir / module_path).mkdir(parents=True)
    (repo_dir / module_path / "notebook.ipynb").write_text("nb")
    (repo_dir / module_path / "gromacs.schema.json").write_text("{}")
    (repo_dir / other_path).mkdir(parents=True)
    (repo_dir / other_path / "other.ipynb").write_text("other")
    (repo_dir / "README.md").write_text("root readme")

    subprocess.run(["git", "init", "-q", "-b", "main"], cwd=repo_dir, check=True)
    subprocess.run(["git", "config", "user.email", "t@t.test"], cwd=repo_dir, check=True)
    subprocess.run(["git", "config", "user.name", "Test"], cwd=repo_dir, check=True)
    subprocess.run(["git", "add", "-A"], cwd=repo_dir, check=True)
    subprocess.run(["git", "commit", "-q", "-m", "init"], cwd=repo_dir, check=True)


class _FakeProcess:
    """A finished (or never-finishing) git process."""

    def __init__(self, returncode: int, stderr: str = "", hang: bool = False) -> None:
        self.returncode = returncode
        self._stderr = stderr.encode()
        self._hang = hang

    async def communicate(self) -> tuple[bytes, bytes]:
        if self._hang:
            await asyncio.sleep(60)
        return b"", self._stderr

    def kill(self) -> None:
        self.returncode = -9

    async def wait(self) -> int:
        return self.returncode


def _exec_with(handler: Callable[[tuple[str, ...]], _FakeProcess | None]) -> Callable[..., Any]:
    """Fake create_subprocess_exec: `handler` answers a command or returns None to run it for real."""

    async def fake(*cmd: str, **kwargs: Any) -> Any:
        return handler(cmd) or await _real_exec(*cmd, **kwargs)

    return fake


def _is_clone(cmd: tuple[str, ...]) -> bool:
    return cmd[:2] == ("git", "clone")


class TestDownloadGitRepoModule:
    """Tests for download_git_repo_module (sparse checkout of a subdirectory)."""

    async def test_copies_only_selected_module_contents_into_target(self, tmp_path: Path) -> None:
        """Only the selected module directory's contents should appear in target_dir."""
        repo = tmp_path / "repo"
        _make_real_repo(repo, "gromacs/protein", "amber/protein")
        target = tmp_path / "target"

        await download_git_repo_module(str(repo), "gromacs/protein", target)

        assert (target / "notebook.ipynb").read_text() == "nb"
        assert (target / "gromacs.schema.json").read_text() == "{}"
        assert not (target / "other.ipynb").exists()
        assert not (target / "README.md").exists()
        assert not (target / ".git").exists()

    async def test_missing_module_path_raises_not_found(self, tmp_path: Path) -> None:
        """A module path absent from the repository should raise NotFound."""
        repo = tmp_path / "repo"
        _make_real_repo(repo, "gromacs/protein", "amber/protein")

        with pytest.raises(NotFound):
            await download_git_repo_module(str(repo), "does/not/exist", tmp_path / "target")

    @pytest.mark.parametrize(
        "stderr",
        ["fatal: auth failure", "fatal: could not read Password for 'http://ghp_secret@github.com':"],
        ids=["plain", "token-echoed-in-url"],
    )
    async def test_clone_failure_redacts_token_from_errors_and_logs(
        self, tmp_path: Path, caplog: pytest.LogCaptureFixture, stderr: str
    ) -> None:
        """Clone failures must not leak the access token in exceptions or logs."""
        with (
            patch("core.utils.asyncio.create_subprocess_exec", _exec_with(lambda _cmd: _FakeProcess(1, stderr))),
            pytest.raises(InternalServerError) as exc_info,
        ):
            await download_git_repo_module(
                "https://github.com/owner/repo.git", "gromacs/protein", tmp_path / "target", access_token="ghp_secret"
            )

        assert "ghp_secret" not in exc_info.value.description
        assert "ghp_secret" not in caplog.text
        if "Password" in stderr:
            assert "***" in exc_info.value.description

    async def test_uses_partial_clone_and_sparse_checkout(self, tmp_path: Path) -> None:
        """The clone should use --no-checkout with blob filtering and sparse checkout."""
        repo = tmp_path / "repo"
        _make_real_repo(repo, "gromacs/protein", "amber/protein")
        captured: list[tuple[str, ...]] = []

        def capture(cmd: tuple[str, ...]) -> None:
            if _is_clone(cmd):
                captured.append(cmd)

        with patch("core.utils.asyncio.create_subprocess_exec", _exec_with(capture)):
            await download_git_repo_module(str(repo), "gromacs/protein", tmp_path / "target")

        assert captured, "expected at least one git clone invocation"
        assert "--no-checkout" in captured[0]
        assert "--filter=blob:none" in captured[0]
        assert "--" in captured[0]

    async def test_falls_back_to_shallow_clone_when_filter_unsupported(self, tmp_path: Path) -> None:
        """When blob filtering fails, fall back to a normal shallow clone then sparse checkout."""
        repo = tmp_path / "repo"
        _make_real_repo(repo, "gromacs/protein", "amber/protein")
        target = tmp_path / "target"
        clones: list[tuple[str, ...]] = []

        def flaky(cmd: tuple[str, ...]) -> _FakeProcess | None:
            if _is_clone(cmd):
                clones.append(cmd)
                if len(clones) == 1:
                    return _FakeProcess(1, "fatal: filter not supported")
            return None

        with patch("core.utils.asyncio.create_subprocess_exec", _exec_with(flaky)):
            await download_git_repo_module(str(repo), "gromacs/protein", target)

        assert len(clones) == 2
        assert (target / "notebook.ipynb").exists()

    async def test_clone_timeout_raises_without_retry(self, tmp_path: Path) -> None:
        """A clone timeout surfaces immediately as InternalServerError; it is not retried."""
        calls: list[tuple[str, ...]] = []

        def hang(cmd: tuple[str, ...]) -> _FakeProcess:
            calls.append(cmd)
            return _FakeProcess(0, hang=True)

        with (
            patch("core.utils.GIT_CLONE_TIMEOUT", 0.05),
            patch("core.utils.asyncio.create_subprocess_exec", _exec_with(hang)),
            pytest.raises(InternalServerError, match="timed out"),
        ):
            await download_git_repo_module("https://github.com/owner/repo.git", "gromacs/protein", tmp_path / "t")

        assert len(calls) == 1
