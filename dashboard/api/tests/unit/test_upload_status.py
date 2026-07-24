"""Unit tests for the durable upload status document."""

from pathlib import Path

import pytest
from upload.status import (
    STATUS_FILENAME,
    FailedFile,
    UploadState,
    UploadStatus,
    create_queued_status,
    read_status,
    status_path,
    write_status,
)


@pytest.fixture
def data_dir(tmp_path: Path) -> Path:
    """Return a temporary data directory for status files."""
    return tmp_path


@pytest.fixture
def experiment_dir(data_dir: Path) -> Path:
    """Return a temporary experiment directory."""
    d = data_dir / "abcde"
    d.mkdir(parents=True)
    return d


def _queued(attempt: str = "att-1") -> UploadStatus:
    return create_queued_status(attempt)


class TestUploadState:
    """Tests for the UploadState enum."""

    def test_terminal_states(self) -> None:
        """COMPLETED and FAILED are terminal."""
        assert UploadState.COMPLETED in UploadState.terminal()
        assert UploadState.FAILED in UploadState.terminal()

    def test_active_states(self) -> None:
        """QUEUED and RUNNING are active (non-terminal)."""
        assert UploadState.QUEUED in UploadState.active()
        assert UploadState.RUNNING in UploadState.active()

    def test_terminal_and_active_disjoint(self) -> None:
        """No state is both terminal and active."""
        assert UploadState.terminal().isdisjoint(UploadState.active())


class TestUploadStatusSerialization:
    """Tests for UploadStatus round-trip serialization."""

    def test_to_dict_and_from_dict_roundtrip(self) -> None:
        """Status document survives serialisation round-trip."""
        status = UploadStatus(
            attempt_id="a1",
            state="running",
            total_files=10,
            completed_files=3,
            total_bytes=1000,
            completed_bytes=300,
            failed_files=[FailedFile(key="bad.txt", error="timeout")],
        )
        restored = UploadStatus.from_dict(status.to_dict())

        assert restored.attempt_id == "a1"
        assert restored.state == "running"
        assert restored.total_files == 10
        assert restored.completed_files == 3
        assert len(restored.failed_files) == 1
        assert restored.failed_files[0].key == "bad.txt"

    def test_from_dict_tolerates_missing_fields(self) -> None:
        """Deserialisation tolerates missing optional fields."""
        restored = UploadStatus.from_dict({"attempt_id": "a1"})
        assert restored.attempt_id == "a1"
        assert restored.state == ""
        assert restored.failed_files == []

    def test_from_dict_truncates_failed_list(self) -> None:
        """Failed files list is bounded."""
        too_many = [{"key": f"f{i}", "error": "err"} for i in range(100)]
        restored = UploadStatus.from_dict({"attempt_id": "a", "failed_files": too_many})
        assert len(restored.failed_files) <= 50


class TestStatusReadWrite:
    """Tests for atomic status file read/write."""

    def test_write_and_read(self, experiment_dir: Path, data_dir: Path) -> None:
        """Written status can be read back."""
        write_status(_queued(), "abcde", data_dir)
        restored = read_status("abcde", data_dir)

        assert restored is not None
        assert restored.attempt_id == "att-1"
        assert restored.state == "queued"

    def test_read_returns_none_when_missing(self, data_dir: Path) -> None:
        """Reading a non-existent status returns None."""
        assert read_status("nonexistent", data_dir) is None

    def test_read_returns_none_on_corrupt(self, experiment_dir: Path, data_dir: Path) -> None:
        """Corrupt JSON returns None instead of raising."""
        (experiment_dir / STATUS_FILENAME).write_text("not json")
        assert read_status("abcde", data_dir) is None

    def test_write_creates_parent_dir(self, data_dir: Path) -> None:
        """Writing creates the experiment directory if it doesn't exist."""
        write_status(_queued(), "newexp", data_dir)
        assert status_path("newexp", data_dir).exists()


class TestAttemptFencing:
    """Tests for attempt-fenced writes."""

    def test_fence_blocks_mismatched_attempt(self, experiment_dir: Path, data_dir: Path) -> None:
        """A writer with a different attempt ID cannot overwrite."""
        write_status(_queued("att-1"), "abcde", data_dir)

        status2 = _queued("att-2")
        result = write_status(status2, "abcde", data_dir, expected_attempt_id="att-2")

        assert result is False
        restored = read_status("abcde", data_dir)
        assert restored is not None
        assert restored.attempt_id == "att-1"

    def test_fence_allows_matching_attempt(self, experiment_dir: Path, data_dir: Path) -> None:
        """A writer with the correct attempt ID can update."""
        write_status(_queued("att-1"), "abcde", data_dir)

        status = _queued("att-1")
        status.state = UploadState.RUNNING.value
        result = write_status(status, "abcde", data_dir, expected_attempt_id="att-1")

        assert result is True
        restored = read_status("abcde", data_dir)
        assert restored is not None
        assert restored.state == "running"

    def test_no_fence_when_expected_none(self, experiment_dir: Path, data_dir: Path) -> None:
        """Without expected_attempt_id, any write succeeds."""
        write_status(_queued("att-1"), "abcde", data_dir)

        result = write_status(_queued("att-2"), "abcde", data_dir)

        assert result is True
        restored = read_status("abcde", data_dir)
        assert restored is not None
        assert restored.attempt_id == "att-2"
