"""Unit tests for upload Job submission."""

from pathlib import Path
from unittest.mock import Mock, patch

import pytest
from upload import submission
from upload.submission import (
    UPLOAD_APP_LABEL,
    SubmissionError,
    build_credential_env,
    is_upload_active,
    job_name,
)


class TestNaming:
    """Tests for deterministic resource naming."""

    def test_job_name_is_deterministic(self) -> None:
        """Same experiment ID produces the same Job name."""
        assert job_name("abcde") == job_name("abcde")

    def test_different_experiments_different_names(self) -> None:
        """Different experiment IDs produce different Job names."""
        assert job_name("abcde") != job_name("fghij")

    def test_job_name_is_dns1123(self) -> None:
        """Job name matches DNS-1123 label requirements."""
        name = job_name("abcde")
        import re

        assert re.match(r"^[a-z0-9]([-a-z0-9]*[a-z0-9])?$", name)


class TestBuildCredentialEnv:
    """Tests for converting credential data to container env."""

    def test_env_contains_oauth_fields(self) -> None:
        """Env list includes all OAuth fields with correct names."""
        env = build_credential_env({
            "access_token": "at",
            "refresh_token": "rt",
            "expires_at": "12345.0",
            "client_id": "cid",
            "client_secret": "cs",
            "api_url": "https://mdrepo/api",
            "record_name": "datasets",
            "token_url": "https://mdrepo/oauth/token",
        })
        by_name = {e["name"]: e["value"] for e in env}
        assert by_name["MDREPO_ACCESS_TOKEN"] == "at"
        assert by_name["MDREPO_REFRESH_TOKEN"] == "rt"
        assert by_name["MDREPO_TOKEN_EXPIRES_AT"] == "12345.0"
        assert by_name["MDREPO_CLIENT_ID"] == "cid"
        assert by_name["MDREPO_CLIENT_SECRET"] == "cs"
        assert by_name["MDREPO_API_URL"] == "https://mdrepo/api"
        assert by_name["MDREPO_RECORD_NAME"] == "datasets"
        assert by_name["MDREPO_TOKEN_URL"] == "https://mdrepo/oauth/token"


class TestIsUploadActive:
    """Tests for is_upload_active."""

    @patch("upload.submission.k8s.read_job")
    def test_returns_true_when_job_active(self, mock_read: Mock) -> None:
        """Active Job (status.active > 0) returns True."""
        mock_read.return_value = Mock(status=Mock(active=1))
        assert is_upload_active("abcde") is True

    @patch("upload.submission.k8s.read_job")
    def test_returns_false_when_job_not_found(self, mock_read: Mock) -> None:
        """Missing Job returns False."""
        mock_read.return_value = None
        assert is_upload_active("abcde") is False

    @patch("upload.submission.k8s.read_job")
    def test_returns_false_when_job_finished(self, mock_read: Mock) -> None:
        """Completed Job (status.active = 0) returns False."""
        mock_read.return_value = Mock(status=Mock(active=0))
        assert is_upload_active("abcde") is False


class TestSubmitUploadJob:
    """Tests for the submit_upload_job flow."""

    @patch("upload.submission.is_upload_active", return_value=True)
    @patch("upload.submission.read_status")
    def test_returns_existing_attempt_when_active(self, mock_read: Mock, mock_active: Mock, tmp_path: Path) -> None:
        """When a Job is already active, returns the existing attempt ID."""
        mock_read.return_value = Mock(attempt_id="existing-att")
        result = submission.submit_upload_job(
            experiment_id="abcde",
            mdrepo_id="rec1",
            credential_data={},
            data_dir=tmp_path,
        )
        assert result == "existing-att"

    @patch("upload.submission.delete_upload_resources")
    @patch("upload.submission.is_upload_active", return_value=False)
    @patch("upload.submission.read_status", return_value=None)
    @patch("upload.submission.write_status")
    @patch("upload.submission.create_queued_status")
    @patch("upload.submission.k8s")
    def test_creates_job_with_env_credentials_and_waits_for_admission(
        self,
        mock_k8s: Mock,
        mock_create_queued: Mock,
        mock_write: Mock,
        mock_read: Mock,
        mock_active: Mock,
        mock_delete: Mock,
        tmp_path: Path,
    ) -> None:
        """Full submission creates Job with env credentials and waits for pod admission."""
        mock_k8s.wait_for_pod_admission.return_value = True
        mock_create_queued.return_value = Mock()

        credential_data = {
            "access_token": "tok",
            "refresh_token": "rt",
            "client_id": "cid",
            "client_secret": "cs",
            "api_url": "https://mdrepo/api",
            "token_url": "https://mdrepo/oauth/token",
        }

        result = submission.submit_upload_job(
            experiment_id="abcde",
            mdrepo_id="rec1",
            credential_data=credential_data,
            data_dir=tmp_path,
        )

        # Returns a non-empty attempt ID.
        assert len(result) == 16  # secrets.token_hex(8) = 16 hex chars

        # Job was created.
        mock_k8s.create_job_raw.assert_called_once()
        job_manifest = mock_k8s.create_job_raw.call_args[0][0]
        assert job_manifest["kind"] == "Job"
        assert job_manifest["spec"]["backoffLimit"] == 0
        assert job_manifest["spec"]["ttlSecondsAfterFinished"] == 300

        # Credentials passed via container env.
        container = job_manifest["spec"]["template"]["spec"]["containers"][0]
        by_name = {e["name"]: e["value"] for e in container["env"]}
        assert by_name["MDREPO_ACCESS_TOKEN"] == "tok"
        assert by_name["MDREPO_CLIENT_SECRET"] == "cs"

        # Pod admission was waited for.
        mock_k8s.wait_for_pod_admission.assert_called_once()

        # Old resources were cleaned up before creating new ones.
        mock_delete.assert_called_once()

    @patch("upload.submission.delete_upload_resources")
    @patch("upload.submission.is_upload_active", return_value=False)
    @patch("upload.submission.read_status", return_value=None)
    @patch("upload.submission.write_status")
    @patch("upload.submission.create_queued_status")
    @patch("upload.submission.k8s")
    def test_admission_timeout_cleans_up(
        self,
        mock_k8s: Mock,
        mock_create_queued: Mock,
        mock_write: Mock,
        mock_read: Mock,
        mock_active: Mock,
        mock_delete: Mock,
        tmp_path: Path,
    ) -> None:
        """Admission timeout foreground-deletes resources and raises."""
        mock_k8s.wait_for_pod_admission.return_value = False
        mock_create_queued.return_value = Mock()

        with pytest.raises(SubmissionError, match="not admitted"):
            submission.submit_upload_job(
                experiment_id="abcde",
                mdrepo_id="rec1",
                credential_data={},
                data_dir=tmp_path,
            )

        # Called at least once for the timeout cleanup (also once before creating).
        assert mock_delete.call_count >= 1

    @patch("upload.submission.k8s")
    @patch("upload.submission.is_upload_active", return_value=False)
    @patch("upload.submission.read_status", return_value=None)
    @patch("upload.submission.write_status")
    @patch("upload.submission.create_queued_status")
    @patch("upload.submission.delete_upload_resources")
    def test_job_manifest_has_preserve_label(
        self,
        mock_delete: Mock,
        mock_create_queued: Mock,
        mock_write: Mock,
        mock_read: Mock,
        mock_active: Mock,
        mock_k8s: Mock,
        tmp_path: Path,
    ) -> None:
        """Job and pod template carry the preserve-on-stop label."""
        mock_k8s.wait_for_pod_admission.return_value = True
        mock_create_queued.return_value = Mock()

        submission.submit_upload_job(
            experiment_id="abcde",
            mdrepo_id="rec1",
            credential_data={},
            data_dir=tmp_path,
        )

        job_manifest = mock_k8s.create_job_raw.call_args[0][0]
        labels = job_manifest["metadata"]["labels"]
        assert labels["mddash.io/preserve-on-stop"] == "true"
        assert labels["app"] == UPLOAD_APP_LABEL
        pod_labels = job_manifest["spec"]["template"]["metadata"]["labels"]
        assert pod_labels["mddash.io/preserve-on-stop"] == "true"

    @patch("upload.submission.k8s")
    @patch("upload.submission.is_upload_active", return_value=False)
    @patch("upload.submission.read_status", return_value=None)
    @patch("upload.submission.write_status")
    @patch("upload.submission.create_queued_status")
    @patch("upload.submission.delete_upload_resources")
    def test_job_uses_tokenless_service_account(
        self,
        mock_delete: Mock,
        mock_create_queued: Mock,
        mock_write: Mock,
        mock_read: Mock,
        mock_active: Mock,
        mock_k8s: Mock,
        tmp_path: Path,
    ) -> None:
        """Job disables service account token automount so the pod has no K8s API access."""
        mock_k8s.wait_for_pod_admission.return_value = True
        mock_create_queued.return_value = Mock()

        submission.submit_upload_job(
            experiment_id="abcde",
            mdrepo_id="rec1",
            credential_data={},
            data_dir=tmp_path,
        )

        job_manifest = mock_k8s.create_job_raw.call_args[0][0]
        pod_spec = job_manifest["spec"]["template"]["spec"]
        assert pod_spec["automountServiceAccountToken"] is False
