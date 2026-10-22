"""Tests for lazy dashboard Kubernetes client initialization and pod/service helpers."""

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

import pytest
from clients import Clients
from clients.k8s import K8sClient
from core.enums import JobStatus, PodStatus
from kubernetes_asyncio.client.exceptions import ApiException
from pytest_mock import MockerFixture
from tests.support import pod


def test_constructing_the_client_does_not_load_incluster_config(mocker: MockerFixture) -> None:
    """Building the client (app factory) must not touch Kubernetes configuration."""
    load_config = mocker.patch("kubernetes_asyncio.config.load_incluster_config")

    K8sClient()

    load_config.assert_not_called()


@pytest.fixture
def k8s_lib(mocker: MockerFixture) -> MagicMock:
    """Stand-ins for the lazily imported kubernetes_asyncio symbols (cached per process after first use)."""
    lib = MagicMock()
    lib.ApiClient.return_value.close = AsyncMock()
    for name in ("ApiClient", "CoreV1Api", "BatchV1Api"):
        mocker.patch(f"clients.k8s.{name}", getattr(lib, name), create=True)
    lib.load_config = mocker.patch("kubernetes_asyncio.config.load_incluster_config")
    return lib


def test_apis_share_one_lazily_configured_api_client(k8s_lib: MagicMock) -> None:
    """First Kubernetes use loads in-cluster config once; Core and Batch share the API client."""
    client = K8sClient()

    core = client.core_v1
    assert core is client.core_v1
    batch = client.batch_v1
    assert batch is client.batch_v1

    k8s_lib.load_config.assert_called_once_with()
    k8s_lib.ApiClient.assert_called_once_with()
    k8s_lib.CoreV1Api.assert_called_once_with(k8s_lib.ApiClient.return_value)
    k8s_lib.BatchV1Api.assert_called_once_with(k8s_lib.ApiClient.return_value)


async def test_aclose_closes_and_forgets_the_api_client(k8s_lib: MagicMock) -> None:
    client = K8sClient()
    _ = client.core_v1

    await client.aclose()

    k8s_lib.ApiClient.return_value.close.assert_awaited_once()
    _ = client.core_v1
    assert k8s_lib.ApiClient.call_count == 2


class TestGetPodInfo:
    """get_pod_info maps one pod read to a (status, start_time) tuple."""

    async def test_running_pod_reports_start_time(
        self, mock_k8s: tuple[AsyncMock, AsyncMock], clients: Clients
    ) -> None:
        core, _ = mock_k8s
        started = datetime(2026, 8, 17, 12, 0, tzinfo=UTC)
        core.read_namespaced_pod.return_value = pod("Running", started)

        assert await clients.k8s.get_pod_info("notebook-exp1") == (PodStatus.RUNNING, started)

    async def test_pending_pod_may_lack_start_time(
        self, mock_k8s: tuple[AsyncMock, AsyncMock], clients: Clients
    ) -> None:
        core, _ = mock_k8s
        core.read_namespaced_pod.return_value = pod("Pending", None)

        assert await clients.k8s.get_pod_info("notebook-exp1") == (PodStatus.PENDING, None)

    async def test_missing_pod_is_down_without_start_time(
        self, mock_k8s: tuple[AsyncMock, AsyncMock], clients: Clients
    ) -> None:
        core, _ = mock_k8s
        core.read_namespaced_pod.side_effect = ApiException(status=404)

        assert await clients.k8s.get_pod_info("notebook-exp1") == (PodStatus.DOWN, None)

    async def test_api_error_is_error(self, mock_k8s: tuple[AsyncMock, AsyncMock], clients: Clients) -> None:
        core, _ = mock_k8s
        core.read_namespaced_pod.side_effect = ApiException(status=500)

        assert await clients.k8s.get_pod_info("notebook-exp1") == (PodStatus.ERROR, None)


class TestGetJobStatus:
    """Job conditions and counters map onto JobStatus."""

    async def test_complete_condition_is_finished(
        self, mock_k8s: tuple[AsyncMock, AsyncMock], clients: Clients
    ) -> None:
        _, batch = mock_k8s
        job = MagicMock()
        job.status.conditions = [MagicMock(type="Complete", status="True")]
        batch.read_namespaced_job.return_value = job

        assert await clients.k8s.get_job_status("analysis-x") == JobStatus.FINISHED

    async def test_missing_job_is_unknown(self, mock_k8s: tuple[AsyncMock, AsyncMock], clients: Clients) -> None:
        _, batch = mock_k8s
        batch.read_namespaced_job.side_effect = ApiException(status=404)

        assert await clients.k8s.get_job_status("analysis-x") == JobStatus.UNKNOWN

    async def test_active_job_is_running(self, mock_k8s: tuple[AsyncMock, AsyncMock], clients: Clients) -> None:
        _, batch = mock_k8s
        job = MagicMock()
        job.status.conditions = []
        job.status.succeeded = 0
        job.status.failed = 0
        job.status.active = 1
        batch.read_namespaced_job.return_value = job

        assert await clients.k8s.get_job_status("analysis-x") == JobStatus.RUNNING


async def test_job_logs_decode_raw_bytes(mock_k8s: tuple[AsyncMock, AsyncMock], clients: Clients) -> None:
    """Logs are read unpreloaded and decoded with replacement (truncation can split a character)."""
    core, _ = mock_k8s
    core.list_namespaced_pod.return_value = MagicMock(items=[MagicMock()])
    raw = MagicMock(status=200)
    raw.read = AsyncMock(return_value=b"Running MDDB workflow \xff")
    core.read_namespaced_pod_log.return_value = raw

    logs = await clients.k8s.get_job_logs("analysis-x", tail_lines=5)

    assert logs.startswith("Running MDDB workflow")
    assert core.read_namespaced_pod_log.call_args.kwargs["_preload_content"] is False


@pytest.mark.parametrize("status", [400, 404])
async def test_job_logs_error_status_reads_as_empty(
    mock_k8s: tuple[AsyncMock, AsyncMock], clients: Clients, status: int
) -> None:
    """Unpreloaded reads don't raise: an initializing or vanished pod must not surface Status JSON as logs."""
    core, _ = mock_k8s
    core.list_namespaced_pod.return_value = MagicMock(items=[MagicMock()])
    raw = MagicMock(status=status)
    raw.read = AsyncMock(return_value=b'{"kind":"Status","message":"pod not found"}')
    core.read_namespaced_pod_log.return_value = raw

    assert await clients.k8s.get_job_logs("analysis-x") == ""
    raw.release.assert_called_once()


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

    async def test_service_carries_pod_owner_reference(
        self, mock_k8s: tuple[AsyncMock, AsyncMock], clients: Clients
    ) -> None:
        core, _ = mock_k8s
        core.read_namespaced_service.side_effect = ApiException(status=404)

        await clients.k8s.create_service("svc-exp1", "notebook-exp1", "uid-123")

        self._assert_created_owner_reference(core)

    async def test_existing_service_with_matching_owner_is_kept(
        self, mock_k8s: tuple[AsyncMock, AsyncMock], clients: Clients
    ) -> None:
        core, _ = mock_k8s
        core.read_namespaced_service.return_value = self._existing_service("uid-123")

        await clients.k8s.create_service("svc-exp1", "notebook-exp1", "uid-123")

        core.create_namespaced_service.assert_not_called()
        core.delete_namespaced_service.assert_not_called()

    @pytest.mark.parametrize("uid", ["deleted-pod-uid", None], ids=["stale-owner", "no-owner"])
    async def test_existing_service_with_foreign_owner_is_recreated(
        self,
        mock_k8s: tuple[AsyncMock, AsyncMock],
        uid: str | None,
        clients: Clients,
    ) -> None:
        core, _ = mock_k8s
        core.read_namespaced_service.return_value = self._existing_service(uid)

        await clients.k8s.create_service("svc-exp1", "notebook-exp1", "uid-123")

        core.delete_namespaced_service.assert_called_once()
        self._assert_created_owner_reference(core)

    async def test_gc_removed_stale_service_mid_delete_is_tolerated(
        self,
        mock_k8s: tuple[AsyncMock, AsyncMock],
        clients: Clients,
    ) -> None:
        core, _ = mock_k8s
        core.read_namespaced_service.return_value = self._existing_service("deleted-pod-uid")
        core.delete_namespaced_service.side_effect = ApiException(status=404)

        await clients.k8s.create_service("svc-exp1", "notebook-exp1", "uid-123")

        self._assert_created_owner_reference(core)


class TestCreateNotebookPodUid:
    """create_notebook_pod returns the pod UID for the service owner reference."""

    async def test_returns_uid_of_newly_created_pod(
        self, mock_k8s: tuple[AsyncMock, AsyncMock], clients: Clients
    ) -> None:
        core, _ = mock_k8s
        core.read_namespaced_pod.side_effect = ApiException(status=404)
        core.create_namespaced_pod.return_value.metadata.uid = "new-uid"

        assert await clients.k8s.create_notebook_pod("notebook-exp1", "exp1", "/dash/notebook/exp1", "tok") == "new-uid"

    async def test_returns_uid_of_existing_pod(self, mock_k8s: tuple[AsyncMock, AsyncMock], clients: Clients) -> None:
        core, _ = mock_k8s
        core.read_namespaced_pod.return_value.metadata.uid = "old-uid"

        assert await clients.k8s.create_notebook_pod("notebook-exp1", "exp1", "/dash/notebook/exp1", "tok") == "old-uid"
        core.create_namespaced_pod.assert_not_called()


class TestDeletes:
    """Deletes hit the API directly: a gone resource is deleted, any other API error propagates."""

    async def test_missing_pod_counts_as_deleted(self, mock_k8s: tuple[AsyncMock, AsyncMock], clients: Clients) -> None:
        core, _ = mock_k8s
        core.delete_namespaced_pod.side_effect = ApiException(status=404)

        await clients.k8s.delete_pod("notebook-x")

        core.read_namespaced_pod.assert_not_called()

    async def test_forbidden_delete_propagates(self, mock_k8s: tuple[AsyncMock, AsyncMock], clients: Clients) -> None:
        _, batch = mock_k8s
        batch.delete_namespaced_job.side_effect = ApiException(status=403)

        with pytest.raises(ApiException):
            await clients.k8s.delete_job("analysis-x")

    async def test_existing_job_is_not_recreated(self, mock_k8s: tuple[AsyncMock, AsyncMock], clients: Clients) -> None:
        _, batch = mock_k8s
        batch.create_namespaced_job.side_effect = ApiException(status=409)

        await clients.k8s.create_job("analysis-x", "image", "exp01", "true")

    async def test_ping_propagates_errors_other_than_missing(
        self, mock_k8s: tuple[AsyncMock, AsyncMock], clients: Clients
    ) -> None:
        _, batch = mock_k8s
        batch.read_namespaced_job.side_effect = ApiException(status=403)

        with pytest.raises(ApiException):
            await clients.k8s.ping_resource("job", "analysis-x")
