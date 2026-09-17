"""Unit tests for the durable archive status document."""

from pathlib import Path

import pytest
from archive.status import (
    STATUS_FILENAME,
    ArchiveState,
    ArchiveStatus,
    create_queued_status,
    read_status,
    status_path,
    write_status,
)


@pytest.fixture
def data_dir(tmp_path: Path) -> Path:
    return tmp_path


@pytest.fixture
def experiment_dir(data_dir: Path) -> Path:
    d = data_dir / "abcde"
    d.mkdir(parents=True)
    return d


def _queued(attempt: str = "att-1", direction: str = "archive") -> ArchiveStatus:
    return create_queued_status(attempt, direction)


class TestArchiveState:
    def test_terminal_states(self) -> None:
        assert ArchiveState.COMPLETED in ArchiveState.terminal()
        assert ArchiveState.FAILED in ArchiveState.terminal()

    def test_active_states(self) -> None:
        assert ArchiveState.QUEUED in ArchiveState.active()
        assert ArchiveState.RUNNING in ArchiveState.active()

    def test_terminal_and_active_disjoint(self) -> None:
        assert ArchiveState.terminal().isdisjoint(ArchiveState.active())


class TestArchiveStatusSerialization:
    def test_roundtrip(self) -> None:
        status = ArchiveStatus(attempt_id="a1", state="running", direction="restore", reason="check")
        restored = ArchiveStatus.from_dict(status.to_dict())
        assert restored.attempt_id == "a1"
        assert restored.state == "running"
        assert restored.direction == "restore"
        assert restored.reason == "check"

    def test_from_dict_tolerates_missing_fields(self) -> None:
        restored = ArchiveStatus.from_dict({"attempt_id": "a1"})
        assert restored.attempt_id == "a1"
        assert restored.state == ""
        assert restored.direction == ""
        assert restored.reason is None

    def test_worker_written_shape_parses(self) -> None:
        """Shape produced by worker.sh printf must round-trip."""
        doc = '{"attempt_id": "deadbeef", "state": "failed", "direction": "archive", "reason": "delta-copy"}'
        import json

        restored = ArchiveStatus.from_dict(json.loads(doc))
        assert restored.attempt_id == "deadbeef"
        assert restored.state == "failed"
        assert restored.reason == "delta-copy"


class TestStatusReadWrite:
    def test_write_and_read(self, experiment_dir: Path, data_dir: Path) -> None:
        write_status(_queued(), "abcde", data_dir)
        restored = read_status("abcde", data_dir)
        assert restored is not None
        assert restored.attempt_id == "att-1"
        assert restored.state == "queued"
        assert restored.direction == "archive"

    def test_read_returns_none_when_missing(self, data_dir: Path) -> None:
        assert read_status("nonexistent", data_dir) is None

    def test_read_returns_none_on_corrupt(self, experiment_dir: Path, data_dir: Path) -> None:
        (experiment_dir / STATUS_FILENAME).write_text("not json")
        assert read_status("abcde", data_dir) is None

    def test_write_creates_parent_dir(self, data_dir: Path) -> None:
        write_status(_queued(), "newexp", data_dir)
        assert status_path("newexp", data_dir).exists()


class TestAttemptFencing:
    def test_fence_blocks_mismatched_attempt(self, experiment_dir: Path, data_dir: Path) -> None:
        write_status(_queued("att-1"), "abcde", data_dir)
        result = write_status(_queued("att-2"), "abcde", data_dir, expected_attempt_id="att-2")
        assert result is False
        restored = read_status("abcde", data_dir)
        assert restored is not None
        assert restored.attempt_id == "att-1"

    def test_fence_allows_matching_attempt(self, experiment_dir: Path, data_dir: Path) -> None:
        write_status(_queued("att-1"), "abcde", data_dir)
        status = _queued("att-1")
        status.state = ArchiveState.RUNNING.value
        result = write_status(status, "abcde", data_dir, expected_attempt_id="att-1")
        assert result is True
        restored = read_status("abcde", data_dir)
        assert restored is not None
        assert restored.state == "running"
