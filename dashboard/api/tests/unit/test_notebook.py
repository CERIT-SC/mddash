"""Unit tests for Notebook.start() quota enforcement and pod info properties."""

from collections.abc import Iterator
from datetime import UTC, datetime
from typing import ClassVar
from unittest.mock import AsyncMock, patch

import pytest
from clients import Clients
from core.config import MAX_NOTEBOOKS
from core.enums import NotebookTier, PodStatus
from core.errors import ApiError, Forbidden
from httpx import AsyncClient
from kubernetes_asyncio.client.exceptions import ApiException
from modules.models import Experiment
from modules.notebooks.models import Notebook
from modules.notebooks.schemas import Notebook as NotebookOut
from modules.notebooks.service import NotebookService
from sqlalchemy.ext.asyncio import AsyncSession


def _make_notebook() -> Notebook:
    return Notebook(
        experiment_id="exp-test", token="test-token", experiment=Experiment(id="exp-test", name="Notebook test")
    )


@pytest.fixture(autouse=True)
def pod_info(clients: Clients) -> Iterator[AsyncMock]:
    """Mock the pod read start() performs after creating the pod."""
    with patch.object(clients.k8s, "get_pod_info", AsyncMock(return_value=(PodStatus.PENDING, None))) as info:
        yield info


@pytest.fixture
def service(clients: Clients) -> NotebookService:
    return NotebookService(clients)


class TestNotebookConfigRoute:
    """GET /notebook-config exposes the concurrent-notebook limit to clients."""

    async def test_includes_concurrent_limit(self, client: AsyncClient) -> None:
        response = await client.get("/dash/api/notebook-config")

        assert response.status_code == 200
        assert response.json()["concurrentLimit"] == MAX_NOTEBOOKS


class TestNotebookPodInfo:
    """status and started_at share one K8s read per refresh."""

    async def test_status_and_started_at_share_one_read(self, pod_info: AsyncMock, service: NotebookService) -> None:
        started = datetime(2026, 8, 17, 12, 0, tzinfo=UTC)
        pod_info.return_value = (PodStatus.RUNNING, started)
        notebook = Notebook(experiment_id="exp1", token="t")

        await service.refresh(notebook)

        assert notebook.status == PodStatus.RUNNING
        assert notebook.started_at == started
        pod_info.assert_awaited_once_with("notebook-exp1")

    async def test_started_at_none_when_pod_down(self, pod_info: AsyncMock, service: NotebookService) -> None:
        pod_info.return_value = (PodStatus.DOWN, None)
        notebook = Notebook(experiment_id="exp1", token="t")

        await service.refresh(notebook)

        assert notebook.status == PodStatus.DOWN
        assert notebook.started_at is None

    async def test_reading_status_before_refresh_fails_loudly(self) -> None:
        with pytest.raises(RuntimeError, match="read before"):
            _ = Notebook(experiment_id="exp1", token="t").status

    async def test_schema_dumps_started_at_as_iso8601(self, pod_info: AsyncMock, service: NotebookService) -> None:
        """started_at matches the contract's format: date-time."""
        started = datetime(2026, 8, 17, 12, 0, tzinfo=UTC)
        pod_info.return_value = (PodStatus.RUNNING, started)
        notebook = Notebook(id=1, experiment_id="exp1", token="t", gpu=False)
        await service.refresh(notebook)

        data = NotebookOut.model_validate(notebook).model_dump(mode="json")

        assert data["started_at"] == "2026-08-17T12:00:00Z"
        assert "_pod_info" not in data


class TestNotebookStartQuotaCheck:
    """Tests for the concurrent-notebook and quota-headroom guards in Notebook.start()."""

    async def test_raises_forbidden_when_concurrent_limit_reached(
        self, service: NotebookService, clients: Clients
    ) -> None:
        """start() must raise a 403 ApiError without creating a pod when notebook count is at the limit."""
        with (
            patch.object(clients.k8s, "count_notebook_pods", return_value=2),
            patch("modules.notebooks.service.MAX_NOTEBOOKS", 2),
            patch.object(clients.k8s, "create_notebook_pod") as mock_create,
        ):
            with pytest.raises(ApiError) as exc_info:
                await service.start(_make_notebook())

            assert exc_info.value.status_code == 403
            assert exc_info.value.problem_type == "urn:mddash:notebook-quota-exceeded"
            mock_create.assert_not_called()

    async def test_raises_forbidden_when_quota_headroom_insufficient(
        self, service: NotebookService, clients: Clients
    ) -> None:
        """start() must raise Forbidden without creating a pod when quota would be exceeded."""
        with (
            patch.object(clients.k8s, "count_notebook_pods", return_value=0),
            patch("modules.notebooks.service.MAX_NOTEBOOKS", 2),
            patch.object(clients.k8s, "check_quota_headroom", return_value="Memory quota exceeded"),
            patch.object(clients.k8s, "create_notebook_pod") as mock_create,
        ):
            with pytest.raises(Forbidden):
                await service.start(_make_notebook())

            mock_create.assert_not_called()

    async def test_creates_pod_when_quota_headroom_sufficient(self, service: NotebookService, clients: Clients) -> None:
        """start() must proceed to pod creation when all quota checks pass."""
        with (
            patch.object(clients.k8s, "count_notebook_pods", return_value=0),
            patch("modules.notebooks.service.MAX_NOTEBOOKS", 2),
            patch.object(clients.k8s, "check_quota_headroom", return_value=None),
            patch.object(clients.k8s, "create_notebook_pod") as mock_create,
            patch.object(clients.k8s, "create_service"),
            patch.object(clients.caddy, "add_proxy_route", return_value="route-id"),
        ):
            await service.start(_make_notebook())

            mock_create.assert_called_once()

    async def test_service_is_owned_by_the_pod(self, service: NotebookService, clients: Clients) -> None:
        with (
            patch.object(clients.k8s, "count_notebook_pods", return_value=0),
            patch("modules.notebooks.service.MAX_NOTEBOOKS", 2),
            patch.object(clients.k8s, "check_quota_headroom", return_value=None),
            patch.object(clients.k8s, "create_notebook_pod", return_value="uid-123"),
            patch.object(clients.k8s, "create_service") as mock_svc,
            patch.object(clients.caddy, "add_proxy_route", return_value="route-id"),
        ):
            await service.start(_make_notebook())

            mock_svc.assert_called_once_with("svc-exp-test", "notebook-exp-test", "uid-123")


class TestNotebookStartTierAndGpu:
    """Tests for tier selection, GPU attachment, and invalid tier handling in Notebook.start()."""

    _MOCK_RESOURCES: ClassVar[dict] = {
        "requests": {"cpu": "200m", "memory": "512Mi"},
        "limits": {"cpu": "2", "memory": "4Gi"},
    }

    async def test_default_tier_uses_small(self, service: NotebookService, clients: Clients) -> None:
        """start() with no tier argument defaults to NotebookTier.SMALL."""
        resources = self._MOCK_RESOURCES
        with (
            patch.object(clients.k8s, "count_notebook_pods", return_value=0),
            patch("modules.notebooks.service.MAX_NOTEBOOKS", 2),
            patch.object(clients.k8s, "check_quota_headroom", return_value=None),
            patch("modules.notebooks.service.get_tier_resources", return_value=resources) as mock_tier_res,
            patch.object(clients.k8s, "create_notebook_pod"),
            patch.object(clients.k8s, "create_service"),
            patch.object(clients.caddy, "add_proxy_route", return_value="route-id"),
        ):
            await service.start(_make_notebook())
            mock_tier_res.assert_called_once_with(NotebookTier.SMALL)

    async def test_selected_tier_scales_resources(self, service: NotebookService, clients: Clients) -> None:
        """start() passes the requested tier to get_tier_resources."""
        resources = self._MOCK_RESOURCES
        with (
            patch.object(clients.k8s, "count_notebook_pods", return_value=0),
            patch("modules.notebooks.service.MAX_NOTEBOOKS", 2),
            patch.object(clients.k8s, "check_quota_headroom", return_value=None),
            patch("modules.notebooks.service.get_tier_resources", return_value=resources) as mock_tier_res,
            patch.object(clients.k8s, "create_notebook_pod"),
            patch.object(clients.k8s, "create_service"),
            patch.object(clients.caddy, "add_proxy_route", return_value="route-id"),
        ):
            await service.start(_make_notebook(), tier=NotebookTier.MEDIUM)
            mock_tier_res.assert_called_once_with(NotebookTier.MEDIUM)

    async def test_gpu_passed_to_create_pod(self, service: NotebookService, clients: Clients) -> None:
        """start() with gpu=True forwards gpu=True to create_notebook_pod."""
        resources = self._MOCK_RESOURCES
        with (
            patch.object(clients.k8s, "count_notebook_pods", return_value=0),
            patch("modules.notebooks.service.MAX_NOTEBOOKS", 2),
            patch("modules.notebooks.service.GPU_TYPE", "nvidia.com/gpu"),
            patch.object(clients.k8s, "check_quota_headroom", return_value=None),
            patch("modules.notebooks.service.get_tier_resources", return_value=resources),
            patch.object(clients.k8s, "create_notebook_pod") as mock_create,
            patch.object(clients.k8s, "create_service"),
            patch.object(clients.caddy, "add_proxy_route", return_value="route-id"),
        ):
            await service.start(_make_notebook(), gpu=True)
            assert mock_create.call_args.kwargs["gpu"] is True

    async def test_invalid_tier_is_rejected_at_the_route(
        self, client: AsyncClient, db_session: AsyncSession, clients: Clients
    ) -> None:
        """An unrecognized tier is a 400 before any pod is created."""
        db_session.add(Experiment(id="exp01", name="Tier", notebook=Notebook(experiment_id="exp01")))
        await db_session.commit()
        with patch.object(clients.k8s, "create_notebook_pod") as mock_create:
            response = await client.post("/dash/api/experiments/exp01/notebook", json={"tier": "99x"})
        assert response.status_code == 400
        mock_create.assert_not_called()


class TestCreateNotebookPodLifecycleFlags:
    """Verify that create_notebook_pod() injects idle-culling flags and MY_POD_NAME into the pod spec."""

    async def test_lifecycle_flags_in_pod_spec(self, mock_k8s: tuple[AsyncMock, AsyncMock], clients: Clients) -> None:
        """create_notebook_pod() must include cull_idle_timeout, shutdown_no_activity_timeout, and MY_POD_NAME."""
        mock_core, _ = mock_k8s
        mock_core.read_namespaced_pod.side_effect = ApiException(status=404)
        await clients.k8s.create_notebook_pod(
            name="notebook-test",
            experiment_id="test",
            prefix="/notebook/test",
            token="tok",
        )

        body = mock_core.create_namespaced_pod.call_args.kwargs["body"]
        jupyter_container = next(c for c in body["spec"]["containers"] if c["name"] == "jupyter")

        assert any("--MappingKernelManager.cull_idle_timeout=" in arg for arg in jupyter_container["command"])
        assert any("--ServerApp.shutdown_no_activity_timeout=" in arg for arg in jupyter_container["command"])
        assert any(
            env.get("name") == "MY_POD_NAME"
            and env.get("valueFrom", {}).get("fieldRef", {}).get("fieldPath") == "metadata.name"
            for env in jupyter_container["env"]
        )
