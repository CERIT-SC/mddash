"""Unit tests for upload Job submission."""

import re
from collections.abc import Iterator
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

import pytest
from modules.publishing import submission
from modules.publishing.submission import (
    UPLOAD_APP_LABEL,
    SubmissionError,
    build_credential_env,
    is_upload_active,
    job_name,
)


@pytest.fixture
def k8s() -> AsyncMock:
    return AsyncMock()


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

    async def test_returns_true_when_job_active(self, k8s: AsyncMock) -> None:
        """Active Job (status.active > 0) returns True."""
        k8s.read_job.return_value = Mock(status=Mock(active=1))
        assert await is_upload_active(k8s, "abcde") is True

    async def test_returns_false_when_job_not_found(self, k8s: AsyncMock) -> None:
        """Missing Job returns False."""
        k8s.read_job.return_value = None
        assert await is_upload_active(k8s, "abcde") is False

    async def test_returns_false_when_job_finished(self, k8s: AsyncMock) -> None:
        """Completed Job (status.active = 0) returns False."""
        k8s.read_job.return_value = Mock(status=Mock(active=0))
        assert await is_upload_active(k8s, "abcde") is False


class TestSubmitUploadJob:
    """Tests for the submit_upload_job flow."""

    @pytest.fixture(autouse=True)
    def env(self) -> Iterator[SimpleNamespace]:
        """Patch a configured uploader image, no live Job, no status doc, and no status writes."""
        target = "modules.publishing.submission"
        with (
            patch(f"{target}.MDREPO_UPLOADER_IMAGE", "registry/mddash-mdrepo-uploader:dev"),
            patch(f"{target}.is_upload_active", return_value=False) as active,
            patch(f"{target}.read_status", return_value=None) as read,
            patch(f"{target}.write_status"),
            patch(f"{target}.create_queued_status"),
            patch(f"{target}.delete_upload_resources") as delete,
        ):
            yield SimpleNamespace(active=active, read=read, delete=delete)

    async def test_returns_existing_attempt_when_active(
        self,
        tmp_path: Path,
        k8s: AsyncMock,
        env: SimpleNamespace,
    ) -> None:
        """When a Job is already active, returns the existing attempt ID."""
        env.active.return_value = True
        env.read.return_value = Mock(attempt_id="existing-att")
        result = await submission.submit_upload_job(
            k8s,
            experiment_id="abcde",
            mdrepo_id="rec1",
            credential_data={},
            data_dir=tmp_path,
        )
        assert result == "existing-att"

    async def test_creates_job_with_env_credentials_and_waits_for_admission(
        self,
        tmp_path: Path,
        k8s: AsyncMock,
        env: SimpleNamespace,
    ) -> None:
        """Full submission creates Job with env credentials and waits for pod admission."""
        k8s.wait_for_pod_admission.return_value = True

        credential_data = {
            "access_token": "tok",
            "refresh_token": "rt",
            "client_id": "cid",
            "client_secret": "cs",
            "api_url": "https://mdrepo/api",
            "token_url": "https://mdrepo/oauth/token",
        }

        result = await submission.submit_upload_job(
            k8s,
            experiment_id="abcde",
            mdrepo_id="rec1",
            credential_data=credential_data,
            data_dir=tmp_path,
        )

        # Returns a non-empty attempt ID.
        assert len(result) == 16  # secrets.token_hex(8) = 16 hex chars

        # Job was created.
        k8s.create_job_raw.assert_called_once()
        job_manifest = k8s.create_job_raw.call_args[0][0]
        assert job_manifest["kind"] == "Job"
        assert job_manifest["spec"]["backoffLimit"] == 0
        assert job_manifest["spec"]["ttlSecondsAfterFinished"] == 300

        # Credentials passed via container env.
        container = job_manifest["spec"]["template"]["spec"]["containers"][0]
        by_name = {e["name"]: e["value"] for e in container["env"]}
        assert by_name["MDREPO_ACCESS_TOKEN"] == "tok"
        assert by_name["MDREPO_CLIENT_SECRET"] == "cs"

        # Pod admission was waited for.
        k8s.wait_for_pod_admission.assert_called_once()

        # Old resources were cleaned up before creating new ones.
        env.delete.assert_called_once()

    async def test_admission_timeout_cleans_up(
        self,
        tmp_path: Path,
        k8s: AsyncMock,
        env: SimpleNamespace,
    ) -> None:
        """Admission timeout foreground-deletes resources and raises."""
        k8s.wait_for_pod_admission.return_value = False

        with pytest.raises(SubmissionError, match="not admitted"):
            await submission.submit_upload_job(
                k8s,
                experiment_id="abcde",
                mdrepo_id="rec1",
                credential_data={},
                data_dir=tmp_path,
            )

        # Called at least once for the timeout cleanup (also once before creating).
        assert env.delete.call_count >= 1

    async def test_job_manifest_has_preserve_label(
        self,
        tmp_path: Path,
        k8s: AsyncMock,
    ) -> None:
        """Job and pod template carry the preserve-on-stop label."""
        k8s.wait_for_pod_admission.return_value = True

        await submission.submit_upload_job(
            k8s,
            experiment_id="abcde",
            mdrepo_id="rec1",
            credential_data={},
            data_dir=tmp_path,
        )

        job_manifest = k8s.create_job_raw.call_args[0][0]
        labels = job_manifest["metadata"]["labels"]
        assert labels["mddash.io/preserve-on-stop"] == "true"
        assert labels["app"] == UPLOAD_APP_LABEL
        pod_labels = job_manifest["spec"]["template"]["metadata"]["labels"]
        assert pod_labels["mddash.io/preserve-on-stop"] == "true"

    async def test_job_uses_tokenless_service_account(
        self,
        tmp_path: Path,
        k8s: AsyncMock,
    ) -> None:
        """Job disables service account token automount so the pod has no K8s API access."""
        k8s.wait_for_pod_admission.return_value = True

        await submission.submit_upload_job(
            k8s,
            experiment_id="abcde",
            mdrepo_id="rec1",
            credential_data={},
            data_dir=tmp_path,
        )

        job_manifest = k8s.create_job_raw.call_args[0][0]
        pod_spec = job_manifest["spec"]["template"]["spec"]
        assert pod_spec["automountServiceAccountToken"] is False
