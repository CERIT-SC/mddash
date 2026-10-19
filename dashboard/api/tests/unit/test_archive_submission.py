"""Unit tests for archive Job submission."""

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

import pytest
from core.cache import archive_status_cache
from modules.archive import submission
from modules.archive.status import STATUS_FILENAME, ArchiveStatus, write_status
from modules.archive.submission import ARCHIVE_APP_LABEL, SubmissionError, is_job_active, job_name


@pytest.fixture
def k8s() -> AsyncMock:
    return AsyncMock()


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

    async def test_true_when_active(self, k8s: AsyncMock) -> None:
        k8s.read_job.return_value = SimpleNamespace(status=SimpleNamespace(active=1, conditions=None))
        assert await is_job_active(k8s, "archive", "abcde") is True

    async def test_true_when_pending(self, k8s: AsyncMock) -> None:
        """active=0 with no conditions is a pod still scheduling/pulling, not a dead Job."""
        k8s.read_job.return_value = SimpleNamespace(status=SimpleNamespace(active=0, conditions=None))
        assert await is_job_active(k8s, "archive", "abcde") is True

    async def test_false_when_missing(self, k8s: AsyncMock) -> None:
        k8s.read_job.return_value = None
        assert await is_job_active(k8s, "archive", "abcde") is False

    async def test_false_when_complete(self, k8s: AsyncMock) -> None:
        conditions = [SimpleNamespace(type="Complete", status="True")]
        k8s.read_job.return_value = SimpleNamespace(status=SimpleNamespace(active=0, conditions=conditions))
        assert await is_job_active(k8s, "archive", "abcde") is False

    async def test_false_when_failed(self, k8s: AsyncMock) -> None:
        conditions = [SimpleNamespace(type="Failed", status="True")]
        k8s.read_job.return_value = SimpleNamespace(status=SimpleNamespace(active=0, conditions=conditions))
        assert await is_job_active(k8s, "archive", "abcde") is False


class TestSubmitJob:
    @patch("modules.archive.submission.ARCHIVE_WORKER_IMAGE", "registry/mddash-archive-worker:dev")
    @patch("modules.archive.submission.is_job_active", return_value=False)
    @patch("modules.archive.submission.read_status", return_value=None)
    @patch("modules.archive.submission.write_status")
    @patch("modules.archive.submission.delete_jobs")
    async def test_archive_manifest_and_flow(
        self,
        mock_delete: Mock,
        mock_write: Mock,
        mock_read: Mock,
        mock_active: Mock,
        tmp_path: Path,
        k8s: AsyncMock,
    ) -> None:
        k8s.wait_for_pod_admission.return_value = True

        attempt = await submission.submit_job(k8s, "archive", "abcde", tmp_path)

        assert len(attempt) == 16
        mock_write.assert_called_once()
        k8s.create_job_raw.assert_called_once()
        manifest = k8s.create_job_raw.call_args[0][0]
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

        k8s.wait_for_pod_admission.assert_called_once()
        mock_delete.assert_called_once()

    @patch("modules.archive.submission.ARCHIVE_WORKER_IMAGE", "registry/mddash-archive-worker:dev")
    @patch("modules.archive.submission.is_job_active", return_value=True)
    @patch("modules.archive.submission.read_status")
    async def test_idempotent_when_active(
        self,
        mock_read: Mock,
        mock_active: Mock,
        tmp_path: Path,
        k8s: AsyncMock,
    ) -> None:
        mock_read.return_value = Mock(attempt_id="existing")
        assert await submission.submit_job(k8s, "archive", "abcde", tmp_path) == "existing"
        k8s.create_job_raw.assert_not_called()

    @patch("modules.archive.submission.ARCHIVE_WORKER_IMAGE", "registry/mddash-archive-worker:dev")
    @patch("modules.archive.submission.is_job_active", return_value=False)
    @patch("modules.archive.submission.read_status", return_value=None)
    @patch("modules.archive.submission.write_status")
    @patch("modules.archive.submission.delete_jobs")
    async def test_admission_timeout_raises(
        self,
        mock_delete: Mock,
        mock_write: Mock,
        mock_read: Mock,
        mock_active: Mock,
        tmp_path: Path,
        k8s: AsyncMock,
    ) -> None:
        k8s.wait_for_pod_admission.return_value = False
        with pytest.raises(SubmissionError, match="not admitted"):
            await submission.submit_job(k8s, "archive", "abcde", tmp_path)

    @patch("modules.archive.submission.is_job_active", return_value=False)
    @patch("modules.archive.submission.ARCHIVE_WORKER_IMAGE", "")
    async def test_missing_image_raises(self, mock_active: Mock, tmp_path: Path, k8s: AsyncMock) -> None:
        with pytest.raises(SubmissionError, match="ARCHIVE_WORKER_IMAGE"):
            await submission.submit_job(k8s, "archive", "abcde", tmp_path)

    @patch("modules.archive.submission.ARCHIVE_WORKER_IMAGE", "registry/mddash-archive-worker:dev")
    @patch("modules.archive.submission.is_job_active", return_value=False)
    @patch("modules.archive.submission.read_status", return_value=None)
    @patch("modules.archive.submission.delete_jobs")
    async def test_create_failure_removes_queued_doc(
        self,
        mock_delete: Mock,
        mock_read: Mock,
        mock_active: Mock,
        tmp_path: Path,
        k8s: AsyncMock,
    ) -> None:
        """A dead Job with a surviving queued doc would freeze the experiment at archiving."""
        k8s.create_job_raw.side_effect = RuntimeError("boom")
        with pytest.raises(SubmissionError):
            await submission.submit_job(k8s, "archive", "abcde", tmp_path)
        assert not (tmp_path / "abcde" / STATUS_FILENAME).exists()

    @patch("modules.archive.submission.ARCHIVE_WORKER_IMAGE", "registry/mddash-archive-worker:dev")
    @patch("modules.archive.submission.is_job_active", return_value=False)
    @patch("modules.archive.submission.read_status", return_value=None)
    @patch("modules.archive.submission.delete_jobs")
    async def test_admission_timeout_removes_queued_doc(
        self,
        mock_delete: Mock,
        mock_read: Mock,
        mock_active: Mock,
        tmp_path: Path,
        k8s: AsyncMock,
    ) -> None:
        k8s.wait_for_pod_admission.return_value = False
        with pytest.raises(SubmissionError, match="not admitted"):
            await submission.submit_job(k8s, "archive", "abcde", tmp_path)
        assert not (tmp_path / "abcde" / STATUS_FILENAME).exists()

    @patch("modules.archive.submission.ARCHIVE_WORKER_IMAGE", "registry/mddash-archive-worker:dev")
    @patch("modules.archive.submission.is_job_active", return_value=False)
    @patch("modules.archive.submission.read_status", return_value=None)
    @patch("modules.archive.submission.write_status")
    @patch("modules.archive.submission.delete_jobs")
    async def test_restore_uses_restore_mode(
        self,
        mock_delete: Mock,
        mock_write: Mock,
        mock_read: Mock,
        mock_active: Mock,
        tmp_path: Path,
        k8s: AsyncMock,
    ) -> None:
        k8s.wait_for_pod_admission.return_value = True
        await submission.submit_job(k8s, "restore", "abcde", tmp_path)
        manifest = k8s.create_job_raw.call_args[0][0]
        assert manifest["spec"]["template"]["spec"]["containers"][0]["args"][0] == "restore"

    @patch("modules.archive.submission.ARCHIVE_WORKER_IMAGE", "registry/mddash-archive-worker:dev")
    @patch("modules.archive.submission.is_job_active", return_value=False)
    @patch("modules.archive.submission.read_status", return_value=None)
    @patch("modules.archive.submission.write_status")
    @patch("modules.archive.submission.delete_jobs")
    async def test_waits_for_old_job_deletion_before_create(
        self,
        mock_delete: Mock,
        mock_write: Mock,
        mock_read: Mock,
        mock_active: Mock,
        tmp_path: Path,
        k8s: AsyncMock,
    ) -> None:
        """A retry races the foreground-deleted terminal Job (409 "object is being deleted")."""
        k8s.wait_for_pod_admission.return_value = True
        await submission.submit_job(k8s, "archive", "abcde", tmp_path)
        k8s.wait_for_resource_absence.assert_called_once()
        args, kwargs = k8s.wait_for_resource_absence.call_args
        assert args[:2] == ("job", "archive-abcde")
        assert kwargs["max_wait"] > 0

    @patch("modules.archive.submission.ARCHIVE_WORKER_IMAGE", "registry/mddash-archive-worker:dev")
    @patch("modules.archive.submission.is_job_active", return_value=False)
    @patch("modules.archive.submission.read_status", return_value=None)
    @patch("modules.archive.submission.write_status")
    @patch("modules.archive.submission.delete_jobs")
    async def test_still_terminating_old_job_raises_before_doc_write(
        self,
        mock_delete: Mock,
        mock_write: Mock,
        mock_read: Mock,
        mock_active: Mock,
        tmp_path: Path,
        k8s: AsyncMock,
    ) -> None:
        k8s.wait_for_resource_absence.return_value = False
        with pytest.raises(SubmissionError, match="still terminating"):
            await submission.submit_job(k8s, "archive", "abcde", tmp_path)
        k8s.create_job_raw.assert_not_called()
        mock_write.assert_not_called()

    @patch("modules.archive.submission.ARCHIVE_WORKER_IMAGE", "registry/mddash-archive-worker:dev")
    @patch("modules.archive.submission.is_job_active", return_value=False)
    @patch("modules.archive.submission.read_status", return_value=None)
    @patch("modules.archive.submission.delete_jobs")
    async def test_restore_create_failure_keeps_sentinel_doc(
        self,
        mock_delete: Mock,
        mock_read: Mock,
        mock_active: Mock,
        tmp_path: Path,
        k8s: AsyncMock,
    ) -> None:
        """The previous attempt's FAILED restore sentinel must survive submission failures."""
        sentinel = tmp_path / "abcde"
        sentinel.mkdir()
        write_status(
            ArchiveStatus(attempt_id="old", state="failed", direction="restore", reason="copy"), "abcde", tmp_path
        )
        k8s.create_job_raw.side_effect = RuntimeError("boom")
        with pytest.raises(SubmissionError):
            await submission.submit_job(k8s, "restore", "abcde", tmp_path)
        assert (tmp_path / "abcde" / STATUS_FILENAME).exists()

    @patch("modules.archive.submission.ARCHIVE_WORKER_IMAGE", "registry/mddash-archive-worker:dev")
    @patch("modules.archive.submission.is_job_active", return_value=False)
    @patch("modules.archive.submission.read_status", return_value=None)
    @patch("modules.archive.submission.delete_jobs")
    async def test_restore_admission_timeout_keeps_sentinel_doc(
        self,
        mock_delete: Mock,
        mock_read: Mock,
        mock_active: Mock,
        tmp_path: Path,
        k8s: AsyncMock,
    ) -> None:
        sentinel = tmp_path / "abcde"
        sentinel.mkdir()
        write_status(
            ArchiveStatus(attempt_id="old", state="failed", direction="restore", reason="copy"), "abcde", tmp_path
        )
        k8s.wait_for_pod_admission.return_value = False
        with pytest.raises(SubmissionError, match="not admitted"):
            await submission.submit_job(k8s, "restore", "abcde", tmp_path)
        assert (tmp_path / "abcde" / STATUS_FILENAME).exists()

    @patch("modules.archive.submission.ARCHIVE_WORKER_IMAGE", "registry/mddash-archive-worker:dev")
    @patch("modules.archive.submission.is_job_active", return_value=False)
    @patch("modules.archive.submission.read_status", return_value=None)
    @patch("modules.archive.submission.write_status")
    @patch("modules.archive.submission.delete_jobs")
    async def test_successful_submit_writes_through_liveness_cache(
        self,
        mock_delete: Mock,
        mock_write: Mock,
        mock_read: Mock,
        mock_active: Mock,
        tmp_path: Path,
        k8s: AsyncMock,
    ) -> None:
        """The first reconciliation after the 202 must see the new Job live."""
        archive_status_cache.clear()
        k8s.wait_for_pod_admission.return_value = True
        await submission.submit_job(k8s, "restore", "abcde", tmp_path)
        assert archive_status_cache["restore", "abcde"] is True
        archive_status_cache.clear()

    @patch("modules.archive.submission.ARCHIVE_WORKER_IMAGE", "registry/mddash-archive-worker:dev")
    @patch("modules.archive.submission.write_status")
    async def test_purge_writes_no_status_doc(self, mock_write: Mock, k8s: AsyncMock) -> None:
        await submission.submit_purge_job(k8s, "abcde")
        mock_write.assert_not_called()
        k8s.create_job_raw.assert_called_once()
        manifest = k8s.create_job_raw.call_args[0][0]
        assert manifest["spec"]["template"]["spec"]["containers"][0]["args"][0] == "purge"

    @patch("modules.archive.submission.ARCHIVE_WORKER_IMAGE", "")
    async def test_purge_skips_without_image(self, k8s: AsyncMock) -> None:
        await submission.submit_purge_job(k8s, "abcde")
        k8s.create_job_raw.assert_not_called()


class TestDeleteJobs:
    async def test_deletes_all_directions(self, k8s: AsyncMock) -> None:
        await submission.delete_jobs(k8s, "abcde")
        assert k8s.delete_job_foreground.call_count == 3
