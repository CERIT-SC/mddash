"""Unit tests for upload Job submission."""

from unittest.mock import Mock, patch

import pytest
from upload import submission
from upload.submission import (
    UPLOAD_APP_LABEL,
    SubmissionError,
    build_credential_secret_data,
    is_upload_active,
    job_name,
    secret_name,
)


class TestNaming:
    """Tests for deterministic resource naming."""

    def test_job_name_is_deterministic(self) -> None:
        """Same experiment ID produces the same Job name."""
        assert job_name("abcde") == job_name("abcde")

    def test_different_experiments_different_names(self) -> None:
        """Different experiment IDs produce different Job names."""
        assert job_name("abcde") != job_name("fghij")

    def test_secret_name_is_deterministic(self) -> None:
        """Same experiment ID produces the same Secret name."""
        assert secret_name("abcde") == secret_name("abcde")

    def test_job_and_secret_names_differ(self) -> None:
        """Job and Secret names are distinct."""
        assert job_name("abcde") != secret_name("abcde")

    def test_job_name_is_dns1123(self) -> None:
        """Job name matches DNS-1123 label requirements."""
        name = job_name("abcde")
        import re

        assert re.match(r"^[a-z0-9]([-a-z0-9]*[a-z0-9])?$", name)


class TestBuildCredentials:
    """Tests for credential Secret data building."""

    def test_credentials_contain_oauth_fields(self) -> None:
        """Credential data includes all OAuth fields."""
        data = build_credential_secret_data(
            access_token="at",
            refresh_token="rt",
            token_expires_at=12345.0,
            client_id="cid",
            client_secret="cs",
            api_url="https://mdrepo/api",
            record_name="datasets",
            token_url="https://mdrepo/oauth/token",
        )
        assert data["MDREPO_ACCESS_TOKEN"] == "at"
        assert data["MDREPO_REFRESH_TOKEN"] == "rt"
        assert data["MDREPO_TOKEN_EXPIRES_AT"] == "12345.0"
        assert data["MDREPO_CLIENT_ID"] == "cid"
        assert data["MDREPO_CLIENT_SECRET"] == "cs"
        assert data["MDREPO_API_URL"] == "https://mdrepo/api"
        assert data["MDREPO_TOKEN_URL"] == "https://mdrepo/oauth/token"

    def test_credentials_do_not_contain_experiment_or_attempt(self) -> None:
        """Experiment/draft/attempt IDs are NOT in the Secret (passed via CLI args)."""
        data = build_credential_secret_data(
            access_token="at",
            refresh_token="rt",
            token_expires_at=0,
            client_id="cid",
            client_secret="cs",
            api_url="url",
            record_name="datasets",
            token_url="url",
        )
        assert "MDREPO_EXPERIMENT_ID" not in data
        assert "MDREPO_DRAFT_ID" not in data
        assert "MDREPO_ATTEMPT_ID" not in data


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
    def test_returns_existing_attempt_when_active(self, mock_read: Mock, mock_active: Mock, tmp_path: object) -> None:
        """When a Job is already active, returns the existing attempt ID."""
        from pathlib import Path

        mock_read.return_value = Mock(attempt_id="existing-att")
        result = submission.submit_upload_job(
            experiment_id="abcde",
            mdrepo_id="rec1",
            credential_data={},
            data_dir=Path("/tmp"),
        )
        assert result == "existing-att"

    @patch("upload.submission.delete_upload_resources")
    @patch("upload.submission.is_upload_active", return_value=False)
    @patch("upload.submission.read_status", return_value=None)
    @patch("upload.submission.write_status")
    @patch("upload.submission.create_queued_status")
    @patch("upload.submission.k8s")
    def test_creates_secret_and_job_and_waits_for_admission(
        self,
        mock_k8s: Mock,
        mock_create_queued: Mock,
        mock_write: Mock,
        mock_read: Mock,
        mock_active: Mock,
        mock_delete: Mock,
        tmp_path: object,
    ) -> None:
        """Full submission creates Secret, Job, and waits for pod admission."""
        from pathlib import Path

        mock_k8s.wait_for_pod_admission.return_value = True
        mock_create_queued.return_value = Mock()

        result = submission.submit_upload_job(
            experiment_id="abcde",
            mdrepo_id="rec1",
            credential_data={"MDREPO_ACCESS_TOKEN": "tok"},
            data_dir=Path("/tmp"),
        )

        # Returns a non-empty attempt ID.
        assert len(result) == 16  # secrets.token_hex(8) = 16 hex chars

        # Secret was created.
        mock_k8s.create_secret.assert_called_once()

        # Job was created.
        mock_k8s.create_job_raw.assert_called_once()
        job_manifest = mock_k8s.create_job_raw.call_args[0][0]
        assert job_manifest["kind"] == "Job"
        assert job_manifest["spec"]["backoffLimit"] == 0
        assert job_manifest["spec"]["ttlSecondsAfterFinished"] == 300

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
        tmp_path: object,
    ) -> None:
        """Admission timeout foreground-deletes resources and raises."""
        from pathlib import Path

        mock_k8s.wait_for_pod_admission.return_value = False
        mock_create_queued.return_value = Mock()

        with pytest.raises(SubmissionError, match="not admitted"):
            submission.submit_upload_job(
                experiment_id="abcde",
                mdrepo_id="rec1",
                credential_data={},
                data_dir=Path("/tmp"),
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
        tmp_path: object,
    ) -> None:
        """Job and pod template carry the preserve-on-stop label."""
        from pathlib import Path

        mock_k8s.wait_for_pod_admission.return_value = True
        mock_create_queued.return_value = Mock()

        submission.submit_upload_job(
            experiment_id="abcde",
            mdrepo_id="rec1",
            credential_data={},
            data_dir=Path("/tmp"),
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
        tmp_path: object,
    ) -> None:
        """Job disables service account token automount so the pod has no K8s API access."""
        from pathlib import Path

        mock_k8s.wait_for_pod_admission.return_value = True
        mock_create_queued.return_value = Mock()

        submission.submit_upload_job(
            experiment_id="abcde",
            mdrepo_id="rec1",
            credential_data={},
            data_dir=Path("/tmp"),
        )

        job_manifest = mock_k8s.create_job_raw.call_args[0][0]
        pod_spec = job_manifest["spec"]["template"]["spec"]
        assert pod_spec["automountServiceAccountToken"] is False

    @patch("upload.submission.k8s")
    @patch("upload.submission.is_upload_active", return_value=False)
    @patch("upload.submission.read_status", return_value=None)
    @patch("upload.submission.write_status")
    @patch("upload.submission.create_queued_status")
    @patch("upload.submission.delete_upload_resources")
    def test_credentials_via_envfrom_not_embedded(
        self,
        mock_delete: Mock,
        mock_create_queued: Mock,
        mock_write: Mock,
        mock_read: Mock,
        mock_active: Mock,
        mock_k8s: Mock,
        tmp_path: object,
    ) -> None:
        """Credentials are referenced via envFrom, not embedded in the manifest."""
        from pathlib import Path

        mock_k8s.wait_for_pod_admission.return_value = True
        mock_create_queued.return_value = Mock()

        submission.submit_upload_job(
            experiment_id="abcde",
            mdrepo_id="rec1",
            credential_data={"MDREPO_ACCESS_TOKEN": "secret-tok"},
            data_dir=Path("/tmp"),
        )

        job_manifest = mock_k8s.create_job_raw.call_args[0][0]
        container = job_manifest["spec"]["template"]["spec"]["containers"][0]

        # envFrom references the Secret — credentials are not inline.
        assert "envFrom" in container
        assert container["envFrom"][0]["secretRef"]["name"] == secret_name("abcde")

        # No literal token value in the manifest.
        manifest_json = str(job_manifest)
        assert "secret-tok" not in manifest_json
