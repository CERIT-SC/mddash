"""Unit tests for archive Job submission."""

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

import pytest
from archive import submission
from archive.status import STATUS_FILENAME, ArchiveStatus, write_status
from archive.submission import (
    ARCHIVE_APP_LABEL,
    SubmissionError,
    is_job_active,
    job_name,
)
from cache import archive_status_cache


class TestNaming:
    def test_deterministic_per_direction(self) -> None:
        assert job_name("archive", "abcde") == job_name("archive", "abcde")
        assert job_name("archive", "abcde") != job_name("restore", "abcde")
        assert job_name("restore", "abcde") != job_name("purge", "abcde")

    def test_dns1123(self) -> None:
        import re

        for direction in ("archive", "restore", "purge"):
            assert re.match(r"^[a-z0-9]([-a-z0-9]*[a-z0-9])?$", job_name(direction, "abcde"))

    def test_distinct_experiments(self) -> None:
        assert job_name("archive", "abcde") != job_name("archive", "fghij")


class TestIsJobActive:
    """Liveness means "no terminal condition": Pending pods must read as live."""

    @patch("archive.submission.k8s.read_job")
    def test_true_when_active(self, mock_read: Mock) -> None:
        mock_read.return_value = SimpleNamespace(status=SimpleNamespace(active=1, conditions=None))
        assert is_job_active("archive", "abcde") is True

    @patch("archive.submission.k8s.read_job")
    def test_true_when_pending(self, mock_read: Mock) -> None:
        """active=0 with no conditions is a pod still scheduling/pulling, not a dead Job."""
        mock_read.return_value = SimpleNamespace(status=SimpleNamespace(active=0, conditions=None))
        assert is_job_active("archive", "abcde") is True

    @patch("archive.submission.k8s.read_job")
    def test_false_when_missing(self, mock_read: Mock) -> None:
        mock_read.return_value = None
        assert is_job_active("archive", "abcde") is False

    @patch("archive.submission.k8s.read_job")
    def test_false_when_complete(self, mock_read: Mock) -> None:
        conditions = [SimpleNamespace(type="Complete", status="True")]
        mock_read.return_value = SimpleNamespace(status=SimpleNamespace(active=0, conditions=conditions))
        assert is_job_active("archive", "abcde") is False

    @patch("archive.submission.k8s.read_job")
    def test_false_when_failed(self, mock_read: Mock) -> None:
        conditions = [SimpleNamespace(type="Failed", status="True")]
        mock_read.return_value = SimpleNamespace(status=SimpleNamespace(active=0, conditions=conditions))
        assert is_job_active("archive", "abcde") is False


class TestSubmitJob:
    @patch("archive.submission.k8s")
    @patch("archive.submission.ARCHIVE_WORKER_IMAGE", "registry/mddash-archive-worker:dev")
    @patch("archive.submission.is_job_active", return_value=False)
    @patch("archive.submission.read_status", return_value=None)
    @patch("archive.submission.write_status")
    @patch("archive.submission.delete_jobs")
    def test_archive_manifest_and_flow(
        self,
        mock_delete: Mock,
        mock_write: Mock,
        mock_read: Mock,
        mock_active: Mock,
        mock_k8s: Mock,
        tmp_path: Path,
    ) -> None:
        mock_k8s.wait_for_pod_admission.return_value = True

        attempt = submission.submit_job("archive", "abcde", tmp_path)

        assert len(attempt) == 16
        mock_write.assert_called_once()
        mock_k8s.create_job_raw.assert_called_once()
        manifest = mock_k8s.create_job_raw.call_args[0][0]
        assert manifest["spec"]["backoffLimit"] == 0
        assert manifest["spec"]["ttlSecondsAfterFinished"] == 300

        labels = manifest["metadata"]["labels"]
        assert labels["app"] == ARCHIVE_APP_LABEL
        assert labels["mddash.io/preserve-on-stop"] == "true"

        spec = manifest["spec"]["template"]["spec"]
        assert spec["automountServiceAccountToken"] is False

        container = spec["containers"][0]
        args = container["args"]
        assert args[0] == "archive"
        assert "--experiment-id" in args
        assert "abcde" in args
        env = {e["name"] for e in container["env"]}
        assert env == {"S3_BUCKET", "S3_ENDPOINT", "S3_ACCESS_KEY", "S3_SECRET_KEY"}

        mock_k8s.wait_for_pod_admission.assert_called_once()
        mock_delete.assert_called_once()

    @patch("archive.submission.k8s")
    @patch("archive.submission.ARCHIVE_WORKER_IMAGE", "registry/mddash-archive-worker:dev")
    @patch("archive.submission.is_job_active", return_value=True)
    @patch("archive.submission.read_status")
    def test_idempotent_when_active(self, mock_read: Mock, mock_active: Mock, mock_k8s: Mock, tmp_path: Path) -> None:
        mock_read.return_value = Mock(attempt_id="existing")
        assert submission.submit_job("archive", "abcde", tmp_path) == "existing"
        mock_k8s.create_job_raw.assert_not_called()

    @patch("archive.submission.k8s")
    @patch("archive.submission.ARCHIVE_WORKER_IMAGE", "registry/mddash-archive-worker:dev")
    @patch("archive.submission.is_job_active", return_value=False)
    @patch("archive.submission.read_status", return_value=None)
    @patch("archive.submission.write_status")
    @patch("archive.submission.delete_jobs")
    def test_admission_timeout_raises(
        self,
        mock_delete: Mock,
        mock_write: Mock,
        mock_read: Mock,
        mock_active: Mock,
        mock_k8s: Mock,
        tmp_path: Path,
    ) -> None:
        mock_k8s.wait_for_pod_admission.return_value = False
        with pytest.raises(SubmissionError, match="not admitted"):
            submission.submit_job("archive", "abcde", tmp_path)

    @patch("archive.submission.is_job_active", return_value=False)
    @patch("archive.submission.ARCHIVE_WORKER_IMAGE", "")
    def test_missing_image_raises(self, mock_active: Mock, tmp_path: Path) -> None:
        with pytest.raises(SubmissionError, match="ARCHIVE_WORKER_IMAGE"):
            submission.submit_job("archive", "abcde", tmp_path)

    @patch("archive.submission.k8s")
    @patch("archive.submission.ARCHIVE_WORKER_IMAGE", "registry/mddash-archive-worker:dev")
    @patch("archive.submission.is_job_active", return_value=False)
    @patch("archive.submission.read_status", return_value=None)
    @patch("archive.submission.delete_jobs")
    def test_create_failure_removes_queued_doc(
        self, mock_delete: Mock, mock_read: Mock, mock_active: Mock, mock_k8s: Mock, tmp_path: Path
    ) -> None:
        """A dead Job with a surviving queued doc would freeze the experiment at archiving."""
        mock_k8s.create_job_raw.side_effect = RuntimeError("boom")
        with pytest.raises(SubmissionError):
            submission.submit_job("archive", "abcde", tmp_path)
        assert not (tmp_path / "abcde" / STATUS_FILENAME).exists()

    @patch("archive.submission.k8s")
    @patch("archive.submission.ARCHIVE_WORKER_IMAGE", "registry/mddash-archive-worker:dev")
    @patch("archive.submission.is_job_active", return_value=False)
    @patch("archive.submission.read_status", return_value=None)
    @patch("archive.submission.delete_jobs")
    def test_admission_timeout_removes_queued_doc(
        self, mock_delete: Mock, mock_read: Mock, mock_active: Mock, mock_k8s: Mock, tmp_path: Path
    ) -> None:
        mock_k8s.wait_for_pod_admission.return_value = False
        with pytest.raises(SubmissionError, match="not admitted"):
            submission.submit_job("archive", "abcde", tmp_path)
        assert not (tmp_path / "abcde" / STATUS_FILENAME).exists()

    @patch("archive.submission.k8s")
    @patch("archive.submission.ARCHIVE_WORKER_IMAGE", "registry/mddash-archive-worker:dev")
    @patch("archive.submission.is_job_active", return_value=False)
    @patch("archive.submission.read_status", return_value=None)
    @patch("archive.submission.write_status")
    @patch("archive.submission.delete_jobs")
    def test_restore_uses_restore_mode(
        self,
        mock_delete: Mock,
        mock_write: Mock,
        mock_read: Mock,
        mock_active: Mock,
        mock_k8s: Mock,
        tmp_path: Path,
    ) -> None:
        mock_k8s.wait_for_pod_admission.return_value = True
        submission.submit_job("restore", "abcde", tmp_path)
        manifest = mock_k8s.create_job_raw.call_args[0][0]
        assert manifest["spec"]["template"]["spec"]["containers"][0]["args"][0] == "restore"

    @patch("archive.submission.k8s")
    @patch("archive.submission.ARCHIVE_WORKER_IMAGE", "registry/mddash-archive-worker:dev")
    @patch("archive.submission.is_job_active", return_value=False)
    @patch("archive.submission.read_status", return_value=None)
    @patch("archive.submission.write_status")
    @patch("archive.submission.delete_jobs")
    def test_waits_for_old_job_deletion_before_create(
        self,
        mock_delete: Mock,
        mock_write: Mock,
        mock_read: Mock,
        mock_active: Mock,
        mock_k8s: Mock,
        tmp_path: Path,
    ) -> None:
        """A retry races the foreground-deleted terminal Job (409 "object is being deleted")."""
        mock_k8s.wait_for_pod_admission.return_value = True
        submission.submit_job("archive", "abcde", tmp_path)
        mock_k8s.wait_for_resource_absence.assert_called_once()
        args, kwargs = mock_k8s.wait_for_resource_absence.call_args
        assert args[:2] == ("job", "archive-abcde")
        assert kwargs["timeout"] > 0

    @patch("archive.submission.k8s")
    @patch("archive.submission.ARCHIVE_WORKER_IMAGE", "registry/mddash-archive-worker:dev")
    @patch("archive.submission.is_job_active", return_value=False)
    @patch("archive.submission.read_status", return_value=None)
    @patch("archive.submission.write_status")
    @patch("archive.submission.delete_jobs")
    def test_still_terminating_old_job_raises_before_doc_write(
        self,
        mock_delete: Mock,
        mock_write: Mock,
        mock_read: Mock,
        mock_active: Mock,
        mock_k8s: Mock,
        tmp_path: Path,
    ) -> None:
        mock_k8s.wait_for_resource_absence.return_value = False
        with pytest.raises(SubmissionError, match="still terminating"):
            submission.submit_job("archive", "abcde", tmp_path)
        mock_k8s.create_job_raw.assert_not_called()
        mock_write.assert_not_called()

    @patch("archive.submission.k8s")
    @patch("archive.submission.ARCHIVE_WORKER_IMAGE", "registry/mddash-archive-worker:dev")
    @patch("archive.submission.is_job_active", return_value=False)
    @patch("archive.submission.read_status", return_value=None)
    @patch("archive.submission.delete_jobs")
    def test_restore_create_failure_keeps_sentinel_doc(
        self, mock_delete: Mock, mock_read: Mock, mock_active: Mock, mock_k8s: Mock, tmp_path: Path
    ) -> None:
        """The previous attempt's FAILED restore sentinel must survive submission failures."""
        sentinel = tmp_path / "abcde"
        sentinel.mkdir()
        write_status(
            ArchiveStatus(attempt_id="old", state="failed", direction="restore", reason="copy"), "abcde", tmp_path
        )
        mock_k8s.create_job_raw.side_effect = RuntimeError("boom")
        with pytest.raises(SubmissionError):
            submission.submit_job("restore", "abcde", tmp_path)
        assert (tmp_path / "abcde" / STATUS_FILENAME).exists()

    @patch("archive.submission.k8s")
    @patch("archive.submission.ARCHIVE_WORKER_IMAGE", "registry/mddash-archive-worker:dev")
    @patch("archive.submission.is_job_active", return_value=False)
    @patch("archive.submission.read_status", return_value=None)
    @patch("archive.submission.delete_jobs")
    def test_restore_admission_timeout_keeps_sentinel_doc(
        self, mock_delete: Mock, mock_read: Mock, mock_active: Mock, mock_k8s: Mock, tmp_path: Path
    ) -> None:
        sentinel = tmp_path / "abcde"
        sentinel.mkdir()
        write_status(
            ArchiveStatus(attempt_id="old", state="failed", direction="restore", reason="copy"), "abcde", tmp_path
        )
        mock_k8s.wait_for_pod_admission.return_value = False
        with pytest.raises(SubmissionError, match="not admitted"):
            submission.submit_job("restore", "abcde", tmp_path)
        assert (tmp_path / "abcde" / STATUS_FILENAME).exists()

    @patch("archive.submission.k8s")
    @patch("archive.submission.ARCHIVE_WORKER_IMAGE", "registry/mddash-archive-worker:dev")
    @patch("archive.submission.is_job_active", return_value=False)
    @patch("archive.submission.read_status", return_value=None)
    @patch("archive.submission.write_status")
    @patch("archive.submission.delete_jobs")
    def test_successful_submit_writes_through_liveness_cache(
        self,
        mock_delete: Mock,
        mock_write: Mock,
        mock_read: Mock,
        mock_active: Mock,
        mock_k8s: Mock,
        tmp_path: Path,
    ) -> None:
        """The first reconciliation after the 202 must see the new Job live."""
        archive_status_cache.clear()
        mock_k8s.wait_for_pod_admission.return_value = True
        submission.submit_job("restore", "abcde", tmp_path)
        assert archive_status_cache["restore", "abcde"] is True
        archive_status_cache.clear()

    @patch("archive.submission.ARCHIVE_WORKER_IMAGE", "registry/mddash-archive-worker:dev")
    @patch("archive.submission.k8s")
    @patch("archive.submission.write_status")
    def test_purge_writes_no_status_doc(self, mock_write: Mock, mock_k8s: Mock) -> None:
        submission.submit_purge_job("abcde")
        mock_write.assert_not_called()
        mock_k8s.create_job_raw.assert_called_once()
        manifest = mock_k8s.create_job_raw.call_args[0][0]
        assert manifest["spec"]["template"]["spec"]["containers"][0]["args"][0] == "purge"

    @patch("archive.submission.ARCHIVE_WORKER_IMAGE", "")
    @patch("archive.submission.k8s")
    def test_purge_skips_without_image(self, mock_k8s: Mock) -> None:
        submission.submit_purge_job("abcde")
        mock_k8s.create_job_raw.assert_not_called()


class TestDeleteJobs:
    @patch("archive.submission.k8s")
    def test_deletes_all_directions(self, mock_k8s: Mock) -> None:
        submission.delete_jobs("abcde")
        assert mock_k8s.delete_job_foreground.call_count == 3
