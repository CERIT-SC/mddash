"""Unit tests for Datahugger population worker Job submission (deterministic name, no credentials)."""

import json
import re
from unittest.mock import AsyncMock, patch

import pytest
from core.enums import Engine, PopulationStatus
from modules.population.models import PopulationOperation
from modules.population.submission import (
    POPULATION_ADMISSION_TIMEOUT,
    POPULATION_APP_LABEL,
    SubmissionError,
    build_job_manifest,
    job_name,
    submit_population_job,
)

OPERATION_ID = "0123456789abcdef"


def _operation() -> PopulationOperation:
    return PopulationOperation(
        id=OPERATION_ID,
        experiment_id="abcde",
        name="Datahugger Experiment",
        repo_url="https://github.com/test/dataset",
        engine=Engine.GMX,
        job_name=job_name(OPERATION_ID),
        status=PopulationStatus.queued,
    )


@pytest.fixture
def k8s() -> AsyncMock:
    return AsyncMock()


class TestNaming:
    """Tests for deterministic resource naming."""

    def test_job_name_is_deterministic(self) -> None:
        assert job_name(OPERATION_ID) == job_name(OPERATION_ID)

    def test_different_operations_different_names(self) -> None:
        assert job_name(OPERATION_ID) != job_name("fedcba9876543210")

    def test_job_name_is_dns1123(self) -> None:
        assert re.match(r"^[a-z0-9]([-a-z0-9]*[a-z0-9])?$", job_name(OPERATION_ID))


class TestBuildJobManifest:
    """The worker reuses the API image and carries only public arguments."""

    def test_reuses_api_image_and_worker_command(self) -> None:
        with patch("modules.population.submission.API_IMAGE", "registry/mddash-api:dev"):
            manifest = build_job_manifest(_operation())

        container = manifest["spec"]["template"]["spec"]["containers"][0]
        assert container["image"] == "registry/mddash-api:dev"
        assert container["command"] == ["python", "-m", "modules.population.worker"]
        assert container["args"] == [
            "--operation-id",
            OPERATION_ID,
            "--experiment-id",
            "abcde",
            "--repo-url",
            "https://github.com/test/dataset",
        ]

    def test_manifest_carries_only_required_nonsecret_config(self) -> None:
        with patch("modules.population.submission.API_IMAGE", "registry/mddash-api:dev"):
            manifest = build_job_manifest(_operation())

        container = manifest["spec"]["template"]["spec"]["containers"][0]
        # The API's required notebook-limit setting is safe to inherit; no access token belongs here.
        assert container["env"] == [{"name": "NS_MAX_NOTEBOOKS", "value": "2"}]
        assert "access" not in json.dumps(container["args"]).lower()

    def test_worker_job_is_bounded_tokenless_and_non_root(self) -> None:
        with patch("modules.population.submission.API_IMAGE", "registry/mddash-api:dev"):
            manifest = build_job_manifest(_operation())

        assert manifest["kind"] == "Job"
        assert manifest["metadata"]["name"] == job_name(OPERATION_ID)
        assert manifest["metadata"]["labels"]["app"] == POPULATION_APP_LABEL
        assert manifest["metadata"]["labels"]["mddash.io/experiment"] == "abcde"

        spec = manifest["spec"]
        assert spec["backoffLimit"] == 0  # no automatic retries
        assert spec["activeDeadlineSeconds"] == 86400  # 24-hour deadline
        assert spec["ttlSecondsAfterFinished"] == 300

        pod_spec = spec["template"]["spec"]
        assert pod_spec["restartPolicy"] == "Never"
        assert pod_spec["automountServiceAccountToken"] is False
        assert pod_spec["securityContext"]["runAsNonRoot"] is True

        container = pod_spec["containers"][0]
        assert container["securityContext"]["runAsUser"] == 1000
        assert container["securityContext"]["runAsGroup"] == 1000
        assert container["securityContext"]["runAsNonRoot"] is True

        assert pod_spec["volumes"][0]["persistentVolumeClaim"]["claimName"] == "test-pvc"
        assert container["volumeMounts"][0]["mountPath"] == "/mddash"


class TestSubmitPopulationJob:
    """Submission waits for pod admission and cleans up on any failure."""

    async def test_creates_job_and_waits_for_admission(self, k8s: AsyncMock) -> None:
        k8s.wait_for_pod_admission.return_value = True

        await submit_population_job(k8s, _operation())

        k8s.create_job_raw.assert_awaited_once()
        k8s.wait_for_pod_admission.assert_awaited_once_with(
            "mddash.io/experiment=abcde", max_wait=POPULATION_ADMISSION_TIMEOUT
        )

    async def test_unconfigured_api_image_raises(self, k8s: AsyncMock) -> None:
        with (
            patch("modules.population.submission.API_IMAGE", ""),
            pytest.raises(SubmissionError, match="API_IMAGE is not set"),
        ):
            await submit_population_job(k8s, _operation())

        k8s.create_job_raw.assert_not_awaited()

    async def test_admission_timeout_deletes_job_and_raises(self, k8s: AsyncMock) -> None:
        k8s.wait_for_pod_admission.return_value = False

        with pytest.raises(SubmissionError, match="not admitted"):
            await submit_population_job(k8s, _operation())

        k8s.delete_job_foreground.assert_awaited_once_with(job_name(OPERATION_ID))

    async def test_create_failure_deletes_job_and_raises(self, k8s: AsyncMock) -> None:
        k8s.create_job_raw.side_effect = RuntimeError("boom")

        with pytest.raises(SubmissionError, match="Failed to submit"):
            await submit_population_job(k8s, _operation())

        k8s.delete_job_foreground.assert_awaited_once_with(job_name(OPERATION_ID))
