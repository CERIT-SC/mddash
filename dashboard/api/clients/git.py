"""Notebook repository checkouts (git subprocesses with redacted output)."""

import asyncio
import contextlib
import logging
import re
import shutil
import subprocess
import tempfile
from pathlib import Path
from urllib.parse import urlparse

import anyio
from core.errors import InternalServerError, NotFound

logger = logging.getLogger(__name__)

# Timeout for git clone operations (seconds)
GIT_CLONE_TIMEOUT = 120

# Matches the ``://userinfo@`` segment of a URL so captured git stderr can be scrubbed.
_URL_USERINFO_RE = re.compile(r"(://)[^@\s/]+(@)")


async def _clone_repo(git_url: str, target_dir: Path, access_token: str | None = None) -> None:
    """Shallow-clone a git repository into ``target_dir`` (no subdirectory, no ``.git``)."""
    await anyio.Path(target_dir).mkdir(parents=True, exist_ok=True)
    clone_url = _inject_token(git_url, access_token)

    with tempfile.TemporaryDirectory() as tmp_dir:
        clone_dir = Path(tmp_dir) / "repo"
        await _git(
            ["clone", "--depth", "1", "--single-branch", "--no-tags", "--", clone_url, str(clone_dir)],
            label="clone",
            secret=access_token,
        )

        def finish() -> None:
            git_dir = clone_dir / ".git"
            if git_dir.exists():
                shutil.rmtree(git_dir)
            _move_contents(clone_dir, target_dir)

        await anyio.to_thread.run_sync(finish)
        logger.info("Downloaded git repository from %s", git_url)


def _inject_token(git_url: str, access_token: str | None) -> str:
    """
    Inject an access token into an HTTPS git URL for cloning.

    Returns:
        The URL with the token embedded, or the original URL if no token applies.
    """
    if not access_token or git_url.startswith("git@"):
        return git_url
    parsed = urlparse(git_url)
    if parsed.scheme not in {"http", "https"}:
        return git_url
    return parsed._replace(netloc=f"{access_token}@{parsed.netloc}").geturl()


def _redact(text: str | None, secret: str | None) -> str:
    """
    Strip the literal secret and any ``://userinfo@`` segment from git output.

    Returns:
        The scrubbed text.
    """
    if not text:
        return ""
    if secret:
        text = text.replace(secret, "***")
    return _URL_USERINFO_RE.sub(r"\1***\2", text)


async def _git(
    args: list[str], *, cwd: Path | None = None, label: str = "operation", secret: str | None = None
) -> None:
    """
    Run a git subprocess, logging only the redacted stderr.

    Raises:
        InternalServerError: If the git command fails or times out (cause: CalledProcessError/TimeoutExpired).
    """
    proc = await asyncio.create_subprocess_exec("git", *args, cwd=cwd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    try:
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=GIT_CLONE_TIMEOUT)
    except TimeoutError:
        with contextlib.suppress(ProcessLookupError):
            proc.kill()
        await proc.wait()
        raise InternalServerError(f"Git {label} timed out after {GIT_CLONE_TIMEOUT}s") from subprocess.TimeoutExpired(
            ["git", *args], GIT_CLONE_TIMEOUT
        )
    if proc.returncode != 0:
        raw = stderr.decode(errors="replace")
        error = subprocess.CalledProcessError(proc.returncode or 1, ["git", *args], stdout, raw)
        detail = _redact((raw or str(error)).strip(), secret)
        logger.error("Git %s failed: %s", label, detail or "git operation failed")
        raise InternalServerError(f"Git {label} failed: {detail or 'git operation failed'}") from error


def _is_partial_clone_unsupported(exc: BaseException) -> bool:
    """
    Return True when the clone failed because the server rejects partial-clone filtering.

    Returns:
        True for partial-clone failures, False for timeouts/auth/network errors.
    """
    cause = exc.__cause__
    if not isinstance(cause, subprocess.CalledProcessError):
        return False
    stderr = cause.stderr if isinstance(cause.stderr, str) else ""
    text = stderr.lower()
    return "filter" in text or "partial" in text


def _is_outside(path: Path, base: Path) -> bool:
    """
    Return True when ``path`` resolves outside ``base`` (e.g. a symlink escape).

    Returns:
        True if the path escapes the base directory.
    """
    try:
        path.resolve().relative_to(base.resolve())
    except ValueError:
        return True
    return False


def _move_contents(src_dir: Path, target_dir: Path) -> None:
    """Move every entry of ``src_dir`` into ``target_dir``, replacing existing entries."""
    for item in src_dir.iterdir():
        dest = target_dir / item.name
        if dest.exists():
            shutil.rmtree(dest) if dest.is_dir() else dest.unlink()
        shutil.move(item, dest)


async def _clone_repo_module(git_url: str, module_path: str, target_dir: Path, access_token: str | None = None) -> None:
    """
    Sparse-checkout a single module subdirectory into ``target_dir`` (404 when it is missing or escapes the clone).

    Raises:
        InternalServerError: If a git operation fails or times out.
    """
    await anyio.Path(target_dir).mkdir(parents=True, exist_ok=True)
    clone_url = _inject_token(git_url, access_token)

    with tempfile.TemporaryDirectory() as tmp_dir:
        clone_dir = Path(tmp_dir) / "repo"

        try:
            await _git(
                [
                    "clone",
                    "--depth",
                    "1",
                    "--single-branch",
                    "--no-tags",
                    "--no-checkout",
                    "--filter=blob:none",
                    "--",
                    clone_url,
                    str(clone_dir),
                ],
                label="clone",
                secret=access_token,
            )
        except InternalServerError as exc:
            # Retry only on partial-clone-unsupported; surface all other failures.
            if not _is_partial_clone_unsupported(exc):
                raise
            await anyio.to_thread.run_sync(lambda: shutil.rmtree(clone_dir, ignore_errors=True))
            await _git(
                ["clone", "--depth", "1", "--single-branch", "--no-tags", "--", clone_url, str(clone_dir)],
                label="clone",
                secret=access_token,
            )

        # Configure sparse checkout for the selected module directory.
        await _git(
            ["sparse-checkout", "init", "--no-cone"], cwd=clone_dir, label="sparse-checkout init", secret=access_token
        )
        await _git(
            ["sparse-checkout", "set", module_path], cwd=clone_dir, label="sparse-checkout set", secret=access_token
        )
        await _git(["checkout"], cwd=clone_dir, label="checkout", secret=access_token)

        def finish() -> None:
            # Reject symlink/traversal escapes before copying (could move other tenants' data).
            clone_root = clone_dir.resolve()
            module_dir = clone_dir / module_path
            if not module_dir.resolve().is_dir() or _is_outside(module_dir, clone_root):
                raise NotFound(f"Notebook module path '{module_path}' not found in repository.")
            _move_contents(module_dir, target_dir)

        await anyio.to_thread.run_sync(finish)
        logger.info("Downloaded notebook module '%s' from %s", module_path, git_url)


class GitClient:
    """Shallow clones into experiment directories (no subdirectory, no ``.git``)."""

    async def clone(self, git_url: str, target_dir: Path, access_token: str | None = None) -> None:
        """Clone a whole repository into ``target_dir``."""
        await _clone_repo(git_url, target_dir, access_token)

    async def clone_module(
        self, git_url: str, module_path: str, target_dir: Path, access_token: str | None = None
    ) -> None:
        """Sparse-checkout one module subdirectory into ``target_dir`` (404 when it is missing or escapes the clone)."""
        await _clone_repo_module(git_url, module_path, target_dir, access_token)
