"""Integration tests for dashboard/archive-worker/worker.sh using a stubbed rclone."""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

import pytest

API_DIR = Path(__file__).resolve().parents[2]
WORKER = API_DIR.parent / "archive-worker" / "worker.sh"
FILTERS = API_DIR.parent / "s3-sync" / "rclone-filters.txt"

S3_ENV = {
    "S3_BUCKET": "bucket",
    "S3_ENDPOINT": "https://s3.test",
    "S3_ACCESS_KEY": "ak",
    "S3_SECRET_KEY": "sk",
}

RCLONE_STUB = """#!/bin/sh
# Log every invocation; fail commands listed in RCLONE_STUB_FAIL (substring match).
# $1 is the global --config flag, so subcommand checks use $*.
echo "$@" >> "$RCLONE_STUB_LOG"
for pattern in $RCLONE_STUB_FAIL; do
    case "$*" in
        *"$pattern"*) exit 1 ;;
    esac
done
case "$*" in
    *lsf*) [ -n "$RCLONE_STUB_LSF" ] && printf '%s\\n' "$RCLONE_STUB_LSF" ;;
esac
exit 0
"""


@pytest.fixture
def harness(tmp_path: Path) -> dict:
    stub_dir = tmp_path / "bin"
    stub_dir.mkdir()
    rclone = stub_dir / "rclone"
    rclone.write_text(RCLONE_STUB)
    rclone.chmod(0o755)

    data_dir = tmp_path / "mddash"
    exp_dir = data_dir / "exp1"
    exp_dir.mkdir(parents=True)
    (exp_dir / "md.xtc").write_bytes(b"trajectory")
    (exp_dir / "notes.txt").write_text("notes")

    log = tmp_path / "rclone.log"
    env = {
        **os.environ,
        **S3_ENV,
        "PATH": f"{stub_dir}:{os.environ['PATH']}",
        "HOME": str(tmp_path),
        "DATA_DIR": str(data_dir),
        "FILTERS_FILE": str(FILTERS),
        "RCLONE_CONFIG": str(tmp_path / "rclone.conf"),
        "RCLONE_STUB_LOG": str(log),
        "RCLONE_STUB_FAIL": "",
        "RCLONE_STUB_LSF": "",
    }
    return {"data_dir": data_dir, "exp_dir": exp_dir, "log": log, "env": env}


def run(harness: dict, mode: str, fail: str = "", lsf: str = "") -> tuple[subprocess.CompletedProcess, list[str]]:
    env = {**harness["env"], "RCLONE_STUB_FAIL": fail, "RCLONE_STUB_LSF": lsf}
    result = subprocess.run(
        ["sh", str(WORKER), mode, "--experiment-id", "exp1", "--attempt-id", "a1a1"],
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    calls = harness["log"].read_text().splitlines() if harness["log"].exists() else []
    # Strip the leading global "--config <path>" from logged invocations.
    config_prefix = f"--config {env['RCLONE_CONFIG']} "
    return result, [c.removeprefix(config_prefix) for c in calls]


def read_status(harness: dict) -> dict:
    return json.loads((harness["exp_dir"] / ".archive-status.json").read_text())


class TestValidation:
    def test_missing_mode_exits_2(self) -> None:
        result = subprocess.run(["sh", str(WORKER)], capture_output=True, text=True, check=False)
        assert result.returncode == 2
        assert "Usage" in result.stderr

    def test_bad_mode_exits_2(self) -> None:
        result = subprocess.run(["sh", str(WORKER), "bogus"], capture_output=True, text=True, check=False)
        assert result.returncode == 2

    def test_missing_flags_exits_2(self) -> None:
        result = subprocess.run(
            ["sh", str(WORKER), "archive", "--experiment-id", "x"], capture_output=True, text=True, check=False
        )
        assert result.returncode == 2


class TestArchive:
    def test_happy_path(self, harness: dict) -> None:
        result, calls = run(harness, "archive")
        assert result.returncode == 0, result.stderr

        # Server-side seed first, filtered delta second, check before any deletion.
        assert calls[0].startswith("copy s3remote:bucket/exp1 s3remote:bucket/_archives/exp1")
        assert calls[1].startswith("copy ")
        assert "/mddash/exp1" in calls[1]
        assert "_archives/exp1" in calls[1]
        assert "--filter-from" in calls[1]
        assert calls[2].startswith("check s3remote:bucket/_archives/exp1")
        assert "--size-only" in calls[2]

        # The local dir is gone; the completed status doc went with it.
        assert not harness["exp_dir"].exists()

    def test_check_failure_keeps_local_dir(self, harness: dict) -> None:
        # Distinctive check-only marker: " --size-only" appears in no copy call.
        result, _calls = run(harness, "archive", fail="--size-only")
        assert result.returncode == 1
        status = read_status(harness)
        assert status["state"] == "failed"
        assert status["reason"] == "check"
        assert status["direction"] == "archive"
        assert (harness["exp_dir"] / "md.xtc").exists()

    def test_delta_copy_failure_keeps_local_dir(self, harness: dict) -> None:
        # Distinctive delta marker: only the local->S3 copy carries --filter-from.
        result, _calls = run(harness, "archive", fail="--filter-from")
        assert result.returncode == 1
        status = read_status(harness)
        assert status["reason"] == "delta-copy"
        assert (harness["exp_dir"] / "md.xtc").exists()

    def test_seed_copy_failure_keeps_local_dir(self, harness: dict) -> None:
        result, _calls = run(harness, "archive", fail="bucket/exp1")
        assert result.returncode == 1
        assert read_status(harness)["reason"] == "seed-copy"
        assert (harness["exp_dir"] / "md.xtc").exists()

    def test_missing_source_dir_fails(self, harness: dict) -> None:
        harness["exp_dir"].rename(harness["data_dir"] / "elsewhere")
        result, _calls = run(harness, "archive")
        assert result.returncode == 1


class TestRestore:
    def test_refuses_existing_dir(self, harness: dict) -> None:
        result, _calls = run(harness, "restore", lsf="all/keys")
        assert result.returncode == 1
        assert read_status(harness)["reason"] == "target-exists"

    def test_refuses_empty_archive(self, harness: dict) -> None:
        harness["exp_dir"].rename(harness["data_dir"] / "elsewhere")
        result, _calls = run(harness, "restore", lsf="")
        assert result.returncode == 1
        assert read_status(harness)["reason"] == "archive-empty"

    def test_happy_path(self, harness: dict) -> None:
        harness["exp_dir"].rename(harness["data_dir"] / "elsewhere")
        result, calls = run(harness, "restore", lsf="md.xtc")
        assert result.returncode == 0, result.stderr
        assert any(c.startswith("copy s3remote:bucket/_archives/exp1") for c in calls)
        status = read_status(harness)
        assert status["state"] == "completed"
        assert status["direction"] == "restore"

    def _write_sentinel(self, harness: dict, state: str, direction: str) -> None:
        (harness["exp_dir"] / ".archive-status.json").write_text(
            f'{{"attempt_id": "old", "state": "{state}", "direction": "{direction}", "reason": "copy"}}\n'
        )

    def test_failed_sentinel_continues_restore(self, harness: dict) -> None:
        """
        A failed restore leaves its doc plus partial files.

        The retry must resume into that dir, not refuse it as clobber.
        """
        self._write_sentinel(harness, "failed", "restore")
        result, calls = run(harness, "restore", lsf="md.xtc")
        assert result.returncode == 0, result.stderr
        assert any(c.startswith("copy s3remote:bucket/_archives/exp1") for c in calls)
        status = read_status(harness)
        assert status["state"] == "completed"
        assert status["attempt_id"] == "a1a1"

    def test_running_sentinel_continues_restore(self, harness: dict) -> None:
        """An evicted attempt leaves a running doc; it is the same resumable leftover."""
        self._write_sentinel(harness, "running", "restore")
        result, _calls = run(harness, "restore", lsf="md.xtc")
        assert result.returncode == 0, result.stderr

    def test_completed_doc_refuses_to_clobber(self, harness: dict) -> None:
        """A completed restore doc marks a dir that must not be overwritten."""
        self._write_sentinel(harness, "completed", "restore")
        result, _calls = run(harness, "restore", lsf="md.xtc")
        assert result.returncode == 1
        assert read_status(harness)["reason"] == "target-exists"

    def test_archive_direction_doc_refuses_to_clobber(self, harness: dict) -> None:
        """An archive doc in a present dir is foreign to restore: clobber protection."""
        self._write_sentinel(harness, "failed", "archive")
        result, _calls = run(harness, "restore", lsf="md.xtc")
        assert result.returncode == 1
        assert read_status(harness)["reason"] == "target-exists"


class TestPurge:
    def test_purge_calls_rclone_purge(self, harness: dict) -> None:
        result, calls = run(harness, "purge")
        assert result.returncode == 0
        assert calls == ["purge s3remote:bucket/_archives/exp1"]

    def test_purge_writes_no_status_doc(self, harness: dict) -> None:
        run(harness, "purge")
        assert not (harness["exp_dir"] / ".archive-status.json").exists()
