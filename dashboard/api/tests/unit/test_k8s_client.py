"""Tests for lazy dashboard Kubernetes client initialization and pod/service helpers."""

import importlib
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

import pytest
from clients import k8s
from core.enums import JobStatus, PodStatus
from kubernetes_asyncio.client.exceptions import ApiException
from pytest_mock import MockerFixture


def test_importing_k8s_client_does_not_load_incluster_config(mocker: MockerFixture) -> None:
    """Importing the client module should not touch Kubernetes configuration."""
    load_config = mocker.patch("kubernetes_asyncio.config.load_incluster_config")

    importlib.reload(k8s)

    load_config.assert_not_called()
    assert k8s._api_client is None


def test_clients_share_one_lazily_configured_api_client(mocker: MockerFixture) -> None:
    """First Kubernetes use loads in-cluster config once; Core and Batch share the API client."""
    k8s.reset_k8s_clients_for_tests()
    load_config = mocker.patch("kubernetes_asyncio.config.load_incluster_config")
    api_client = mocker.patch("kubernetes_asyncio.client.ApiClient")

    core = k8s.get_core_v1()
    assert core is k8s.get_core_v1()
    batch = k8s.get_batch_v1()
    assert batch is k8s.get_batch_v1()

    load_config.assert_called_once_with()
    api_client.assert_called_once_with()


async def test_aclose_closes_and_forgets_the_api_client(mocker: MockerFixture) -> None:
    k8s.reset_k8s_clients_for_tests()
    mocker.patch("kubernetes_asyncio.config.load_incluster_config")
    api_client = mocker.patch("kubernetes_asyncio.client.ApiClient").return_value
    api_client.close = AsyncMock()
    k8s.get_core_v1()

    await k8s.aclose()

    api_client.close.assert_awaited_once()
    assert k8s._core_v1 is None


def _pod(phase: str, started: datetime | None) -> MagicMock:
    pod = MagicMock()
    pod.metadata.deletion_timestamp = None
    pod.status.phase = phase
    pod.status.container_statuses = []
    pod.status.start_time = started
    return pod


class TestGetPodInfo:
    """get_pod_info maps one pod read to a (status, start_time) tuple."""

    async def test_running_pod_reports_start_time(self, mock_k8s: tuple[AsyncMock, AsyncMock]) -> None:
        core, _ = mock_k8s
        started = datetime(2026, 8, 17, 12, 0, tzinfo=UTC)
        core.read_namespaced_pod.return_value = _pod("Running", started)

        assert await k8s.get_pod_info("notebook-exp1") == (PodStatus.RUNNING, started)

    async def test_pending_pod_may_lack_start_time(self, mock_k8s: tuple[AsyncMock, AsyncMock]) -> None:
        core, _ = mock_k8s
        core.read_namespaced_pod.return_value = _pod("Pending", None)

        assert await k8s.get_pod_info("notebook-exp1") == (PodStatus.PENDING, None)

    async def test_missing_pod_is_down_without_start_time(self, mock_k8s: tuple[AsyncMock, AsyncMock]) -> None:
        core, _ = mock_k8s
        core.read_namespaced_pod.side_effect = ApiException(status=404)

        assert await k8s.get_pod_info("notebook-exp1") == (PodStatus.DOWN, None)

    async def test_api_error_is_error(self, mock_k8s: tuple[AsyncMock, AsyncMock]) -> None:
        core, _ = mock_k8s
        core.read_namespaced_pod.side_effect = ApiException(status=500)

        assert await k8s.get_pod_info("notebook-exp1") == (PodStatus.ERROR, None)


class TestGetJobStatus:
    """Job conditions and counters map onto JobStatus."""

    async def test_complete_condition_is_finished(self, mock_k8s: tuple[AsyncMock, AsyncMock]) -> None:
        _, batch = mock_k8s
        job = MagicMock()
        job.status.conditions = [MagicMock(type="Complete", status="True")]
        batch.read_namespaced_job.return_value = job

        assert await k8s.get_job_status("analysis-x") == JobStatus.FINISHED

    async def test_missing_job_is_unknown(self, mock_k8s: tuple[AsyncMock, AsyncMock]) -> None:
        _, batch = mock_k8s
        batch.read_namespaced_job.side_effect = ApiException(status=404)

        assert await k8s.get_job_status("analysis-x") == JobStatus.UNKNOWN

    async def test_active_job_is_running(self, mock_k8s: tuple[AsyncMock, AsyncMock]) -> None:
        _, batch = mock_k8s
        job = MagicMock()
        job.status.conditions = []
        job.status.succeeded = 0
        job.status.failed = 0
        job.status.active = 1
        batch.read_namespaced_job.return_value = job

        assert await k8s.get_job_status("analysis-x") == JobStatus.RUNNING


async def test_job_logs_decode_raw_bytes(mock_k8s: tuple[AsyncMock, AsyncMock]) -> None:
    """Logs are read unpreloaded and decoded with replacement (truncation can split a character)."""
    core, _ = mock_k8s
    core.list_namespaced_pod.return_value = MagicMock(items=[MagicMock()])
    raw = MagicMock()
    raw.read = AsyncMock(return_value=b"Running MDDB workflow \xff")
    core.read_namespaced_pod_log.return_value = raw

    logs = await k8s.get_job_logs("analysis-x", tail_lines=5)

    assert logs.startswith("Running MDDB workflow")
    assert core.read_namespaced_pod_log.call_args.kwargs["_preload_content"] is False


class TestCreateServiceOwnerReference:
    """The notebook service must be owned by its pod so K8s GC reaps it on pod deletion."""

    def _existing_service(self, uid: str | None) -> MagicMock:
        owner = [] if uid is None else [MagicMock(uid=uid)]
        return MagicMock(metadata=MagicMock(owner_references=owner))

    def _assert_created_owner_reference(self, core: AsyncMock) -> None:
        body = core.create_namespaced_service.call_args.kwargs["body"]
        owner_refs = body.metadata.owner_references
        assert len(owner_refs) == 1
        assert owner_refs[0].api_version == "v1"
        assert owner_refs[0].kind == "Pod"
        assert owner_refs[0].name == "notebook-exp1"
        assert owner_refs[0].uid == "uid-123"

    async def test_service_carries_pod_owner_reference(self, mock_k8s: tuple[AsyncMock, AsyncMock]) -> None:
        core, _ = mock_k8s
        core.read_namespaced_service.side_effect = ApiException(status=404)

        await k8s.create_service("svc-exp1", "notebook-exp1", "uid-123")

        self._assert_created_owner_reference(core)

    async def test_existing_service_with_matching_owner_is_kept(self, mock_k8s: tuple[AsyncMock, AsyncMock]) -> None:
        core, _ = mock_k8s
        core.read_namespaced_service.return_value = self._existing_service("uid-123")

        await k8s.create_service("svc-exp1", "notebook-exp1", "uid-123")

        core.create_namespaced_service.assert_not_called()
        core.delete_namespaced_service.assert_not_called()

    @pytest.mark.parametrize("uid", ["deleted-pod-uid", None], ids=["stale-owner", "no-owner"])
    async def test_existing_service_with_foreign_owner_is_recreated(
        self, mock_k8s: tuple[AsyncMock, AsyncMock], uid: str | None
    ) -> None:
        core, _ = mock_k8s
        core.read_namespaced_service.return_value = self._existing_service(uid)

        await k8s.create_service("svc-exp1", "notebook-exp1", "uid-123")

        core.delete_namespaced_service.assert_called_once()
        self._assert_created_owner_reference(core)

    async def test_gc_removed_stale_service_mid_delete_is_tolerated(
        self, mock_k8s: tuple[AsyncMock, AsyncMock]
    ) -> None:
        core, _ = mock_k8s
        core.read_namespaced_service.return_value = self._existing_service("deleted-pod-uid")
        core.delete_namespaced_service.side_effect = ApiException(status=404)

        await k8s.create_service("svc-exp1", "notebook-exp1", "uid-123")

        self._assert_created_owner_reference(core)


class TestCreateNotebookPodUid:
    """create_notebook_pod returns the pod UID for the service owner reference."""

    async def test_returns_uid_of_newly_created_pod(self, mock_k8s: tuple[AsyncMock, AsyncMock]) -> None:
        core, _ = mock_k8s
        core.read_namespaced_pod.side_effect = ApiException(status=404)
        core.create_namespaced_pod.return_value.metadata.uid = "new-uid"

        assert await k8s.create_notebook_pod("notebook-exp1", "exp1", "/dash/notebook/exp1", "tok") == "new-uid"

    async def test_returns_uid_of_existing_pod(self, mock_k8s: tuple[AsyncMock, AsyncMock]) -> None:
        core, _ = mock_k8s
        core.read_namespaced_pod.return_value.metadata.uid = "old-uid"

        assert await k8s.create_notebook_pod("notebook-exp1", "exp1", "/dash/notebook/exp1", "tok") == "old-uid"
        core.create_namespaced_pod.assert_not_called()
