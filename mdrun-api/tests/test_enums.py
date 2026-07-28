"""Unit tests for enums module."""

import pytest
from enums import DeviceType, JobStatus


class TestJobStatus:
    """Tests for JobStatus enum."""

    def test_all_statuses_exist(self) -> None:
        """Verify all expected status values exist."""
        expected = ["PENDING", "RUNNING", "FINISHED", "ERROR", "UNKNOWN"]
        for status in expected:
            assert hasattr(JobStatus, status)

    def test_status_values(self) -> None:
        """Verify status string values."""
        assert JobStatus.PENDING.value == "pending"
        assert JobStatus.RUNNING.value == "running"
        assert JobStatus.FINISHED.value == "finished"
        assert JobStatus.ERROR.value == "error"
        assert JobStatus.UNKNOWN.value == "unknown"


class TestDeviceType:
    """Tests for DeviceType enum."""

    def test_from_string_valid(self) -> None:
        """Should parse valid device type strings."""
        assert DeviceType.from_string("auto") == DeviceType.AUTO
        assert DeviceType.from_string("cpu") == DeviceType.CPU
        assert DeviceType.from_string("gpu") == DeviceType.GPU

    def test_from_string_case_insensitive(self) -> None:
        """Should handle case variations."""
        assert DeviceType.from_string("AUTO") == DeviceType.AUTO
        assert DeviceType.from_string("Gpu") == DeviceType.GPU

    def test_from_string_invalid(self) -> None:
        """Should raise ValueError for invalid strings."""
        with pytest.raises(ValueError, match="is not a valid DeviceType"):
            DeviceType.from_string("invalid")
