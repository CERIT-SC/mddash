"""Unit tests for selective git checkout of curated notebook modules."""

import subprocess
from pathlib import Path
from typing import TYPE_CHECKING, cast
from unittest.mock import patch

import pytest
from utils import download_git_repo_module
from werkzeug.exceptions import InternalServerError, NotFound

if TYPE_CHECKING:
    from collections.abc import Callable


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


class TestDownloadGitRepoModule:
    """Tests for download_git_repo_module (sparse checkout of a subdirectory)."""

    def test_copies_only_selected_module_contents_into_target(self, tmp_path: Path) -> None:
        """Only the selected module directory's contents should appear in target_dir."""
        repo = tmp_path / "repo"
        _make_real_repo(repo, "gromacs/protein", "amber/protein")

        target = tmp_path / "target"

        download_git_repo_module(str(repo), "gromacs/protein", target)

        assert (target / "notebook.ipynb").read_text() == "nb"
        assert (target / "gromacs.schema.json").read_text() == "{}"
        assert not (target / "other.ipynb").exists()
        assert not (target / "README.md").exists()
        assert not (target / ".git").exists()

    def test_missing_module_path_raises_not_found(self, tmp_path: Path) -> None:
        """A module path absent from the repository should raise NotFound."""
        repo = tmp_path / "repo"
        _make_real_repo(repo, "gromacs/protein", "amber/protein")

        with pytest.raises(NotFound):
            download_git_repo_module(str(repo), "does/not/exist", tmp_path / "target")

    def test_clone_failure_redacts_token_from_errors_and_logs(
        self, tmp_path: Path, caplog: pytest.LogCaptureFixture
    ) -> None:
        """Clone failures must not leak the access token in exceptions or logs."""
        target = tmp_path / "target"
        error = subprocess.CalledProcessError(1, "git")
        error.stderr = "fatal: auth failure"

        with (
            patch("utils.subprocess.run", side_effect=error),
            pytest.raises(InternalServerError) as exc_info,
        ):
            download_git_repo_module(
                "https://github.com/owner/repo.git", "gromacs/protein", target, access_token="ghp_secret"
            )

        assert "ghp_secret" not in str(exc_info.value)
        assert "ghp_secret" not in caplog.text

    def test_clone_timeout_raises_internal_server_error(self, tmp_path: Path) -> None:
        """A clone timeout should raise InternalServerError."""
        target = tmp_path / "target"

        with (
            patch("utils.subprocess.run", side_effect=subprocess.TimeoutExpired(cmd="git", timeout=1)),
            pytest.raises(InternalServerError),
        ):
            download_git_repo_module("https://github.com/owner/repo.git", "gromacs/protein", target)

    def test_uses_partial_clone_and_sparse_checkout(self, tmp_path: Path) -> None:
        """The clone should use --no-checkout with blob filtering and sparse checkout."""
        repo = tmp_path / "repo"
        _make_real_repo(repo, "gromacs/protein", "amber/protein")
        target = tmp_path / "target"

        captured: list[list[str]] = []
        real_run = cast("Callable[..., subprocess.CompletedProcess[str]]", subprocess.run)

        def _capture(cmd: list[str] | str, *args: object, **kwargs: object) -> subprocess.CompletedProcess[str]:
            if isinstance(cmd, list) and cmd[:1] == ["git"] and cmd[1:2] == ["clone"]:
                captured.append(list(cmd))
            return real_run(cmd, *args, **kwargs)

        with patch("utils.subprocess.run", side_effect=_capture):
            download_git_repo_module(str(repo), "gromacs/protein", target)

        assert captured, "expected at least one git clone invocation"
        clone_cmd = captured[0]
        assert "--no-checkout" in clone_cmd
        assert "--filter=blob:none" in clone_cmd
        assert "--" in clone_cmd

    def test_falls_back_to_shallow_clone_when_filter_unsupported(self, tmp_path: Path) -> None:
        """When blob filtering fails, fall back to a normal shallow clone then sparse checkout."""
        repo = tmp_path / "repo"
        _make_real_repo(repo, "gromacs/protein", "amber/protein")
        target = tmp_path / "target"

        original_run = cast("Callable[..., subprocess.CompletedProcess[str]]", subprocess.run)
        call_count = {"clone": 0}

        def _flaky_clone(cmd: list[str] | str, *args: object, **kwargs: object) -> subprocess.CompletedProcess[str]:
            if isinstance(cmd, list) and cmd[:1] == ["git"] and cmd[1:2] == ["clone"]:
                call_count["clone"] += 1
                if call_count["clone"] == 1:
                    raise subprocess.CalledProcessError(1, cmd, stderr="fatal: filter not supported")
            return original_run(cmd, *args, **kwargs)

        with patch("utils.subprocess.run", side_effect=_flaky_clone):
            download_git_repo_module(str(repo), "gromacs/protein", target)

        assert call_count["clone"] == 2
        assert (target / "notebook.ipynb").exists()

    def test_clone_failure_redacts_token_echoed_in_stderr(
        self, tmp_path: Path, caplog: pytest.LogCaptureFixture
    ) -> None:
        """A token echoed by git in the failure URL must be redacted from errors and logs."""
        target = tmp_path / "target"
        # git echoes the authenticated URL (token as userinfo) when it cannot read a password.
        leaked = "fatal: could not read Password for 'http://ghp_secret@github.com':"
        error = subprocess.CalledProcessError(1, "git")
        error.stderr = leaked

        with (
            patch("utils.subprocess.run", side_effect=error),
            pytest.raises(InternalServerError) as exc_info,
        ):
            download_git_repo_module(
                "https://github.com/owner/repo.git", "gromacs/protein", target, access_token="ghp_secret"
            )

        assert "ghp_secret" not in str(exc_info.value)
        assert "ghp_secret" not in caplog.text
        assert "***" in str(exc_info.value)

    def test_clone_timeout_does_not_retry(self, tmp_path: Path) -> None:
        """A clone timeout must surface immediately without a fallback re-clone."""
        target = tmp_path / "target"

        with (
            patch("utils.subprocess.run", side_effect=subprocess.TimeoutExpired(cmd="git", timeout=1)) as mock_run,
            pytest.raises(InternalServerError),
        ):
            download_git_repo_module("https://github.com/owner/repo.git", "gromacs/protein", target)

        # Only the first (filtered) clone attempt runs; the timeout is not retried.
        assert mock_run.call_count == 1
