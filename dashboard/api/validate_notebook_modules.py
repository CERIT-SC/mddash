#!/usr/bin/env python3
"""Deploy-time guard: verify catalog module paths exist as directories in their repos."""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path
from subprocess import CalledProcessError, TimeoutExpired, run

from config import DEFAULT_NOTEBOOKS_REPO
from notebook_modules import load_catalog


def _path_is_tree(repo_url: str, path: str, clone_dir: Path) -> bool:
    """
    Check whether ``path`` is a directory tree in the repo HEAD.

    Returns:
        True if the path is a tree object at HEAD.
    """
    run(
        ["git", "clone", "--depth", "1", "--no-checkout", "--filter=blob:none", "--", repo_url, str(clone_dir)],
        check=True,
        capture_output=True,
        text=True,
        timeout=60,
    )
    result = run(
        ["git", "cat-file", "-t", f"HEAD:{path}"],
        cwd=clone_dir,
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    return result.returncode == 0 and result.stdout.strip() == "tree"


def main() -> int:
    catalog = load_catalog()
    failures: list[str] = []

    for module in catalog:
        if module.is_root:
            continue
        repo_url = module.repository or DEFAULT_NOTEBOOKS_REPO
        with tempfile.TemporaryDirectory() as tmp:
            try:
                if not _path_is_tree(repo_url, module.path, Path(tmp)):
                    failures.append(f"{module.id}: path '{module.path}' not a directory in {repo_url}")
            except (CalledProcessError, TimeoutExpired) as exc:
                failures.append(f"{module.id}: cannot probe {repo_url}: {exc}")

    if failures:
        for f in failures:
            print(f"ERROR: {f}", file=sys.stderr)
        return 1

    non_root = [m for m in catalog if not m.is_root]
    print(f"OK: {len(non_root)} module path(s) verified.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
