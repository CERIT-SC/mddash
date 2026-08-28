"""Unit tests for Notebook.start() quota enforcement and pod info properties."""

from datetime import datetime, timezone
from typing import ClassVar
from unittest.mock import MagicMock, patch

import pytest
from clients.k8s import create_notebook_pod
from config import MAX_NOTEBOOKS
from enums import NotebookTier, PodStatus
from errors import ApiError
from flask.testing import FlaskClient
from models.notebook import Notebook
from schemas.notebook import NotebookSchema
from werkzeug.exceptions import BadRequest, Forbidden


class TestNotebookConfigRoute:
    """GET /notebook-config exposes the concurrent-notebook limit to clients."""

    def test_includes_concurrent_limit(self, client: FlaskClient) -> None:
        response = client.get("/dash/api/notebook-config")

        assert response.status_code == 200
        assert response.get_json()["concurrentLimit"] == MAX_NOTEBOOKS


class TestNotebookPodInfo:
    """status and started_at share one cached K8s read per notebook instance."""

    def test_status_and_started_at_share_one_read(self) -> None:
        started = datetime(2026, 8, 17, 12, 0, tzinfo=timezone.utc)
        notebook = Notebook(experiment_id="exp1", token="t")
        with patch("models.notebook.k8s.get_pod_info", return_value=(PodStatus.RUNNING, started)) as mock_info:
            assert notebook.status == PodStatus.RUNNING
            assert notebook.started_at == started
            mock_info.assert_called_once_with("notebook-exp1")

    def test_started_at_none_when_pod_down(self) -> None:
        notebook = Notebook(experiment_id="exp1", token="t")
        with patch("models.notebook.k8s.get_pod_info", return_value=(PodStatus.DOWN, None)):
            assert notebook.status == PodStatus.DOWN
            assert notebook.started_at is None

    def test_schema_dumps_started_at_as_iso8601(self) -> None:
        """The declared field exists so the property matches the contract's format: date-time."""
        started = datetime(2026, 8, 17, 12, 0, tzinfo=timezone.utc)
        notebook = Notebook(experiment_id="exp1", token="t")
        with patch("models.notebook.k8s.get_pod_info", return_value=(PodStatus.RUNNING, started)):
            data = NotebookSchema().dump(notebook)
        assert data["started_at"] == started.isoformat()
        assert "_pod_info" not in data


class TestNotebookStartQuotaCheck:
    """Tests for the concurrent-notebook and quota-headroom guards in Notebook.start()."""

    def _make_notebook(self) -> MagicMock:
        nb = MagicMock()
        nb.experiment_id = "exp-test"
        nb.token = "test-token"
        return nb

    def test_raises_forbidden_when_concurrent_limit_reached(self) -> None:
        """start() must raise a 403 ApiError without creating a pod when notebook count is at the limit."""
        with (
            patch("models.notebook.k8s.count_notebook_pods", return_value=2),
            patch("models.notebook.MAX_NOTEBOOKS", 2),
            patch("models.notebook.k8s.create_notebook_pod") as mock_create,
        ):
            with pytest.raises(ApiError) as exc_info:
                Notebook.start(self._make_notebook())

            assert exc_info.value.code == 403
            assert exc_info.value.problem_type == "urn:mddash:notebook-quota-exceeded"
            mock_create.assert_not_called()

    def test_raises_forbidden_when_quota_headroom_insufficient(self) -> None:
        """start() must raise Forbidden without creating a pod when quota would be exceeded."""
        with (
            patch("models.notebook.k8s.count_notebook_pods", return_value=0),
            patch("models.notebook.MAX_NOTEBOOKS", 2),
            patch("models.notebook.k8s.check_quota_headroom", return_value="Memory quota exceeded"),
            patch("models.notebook.k8s.create_notebook_pod") as mock_create,
        ):
            with pytest.raises(Forbidden):
                Notebook.start(self._make_notebook())

            mock_create.assert_not_called()

    def test_creates_pod_when_quota_headroom_sufficient(self) -> None:
        """start() must proceed to pod creation when all quota checks pass."""
        with (
            patch("models.notebook.k8s.count_notebook_pods", return_value=0),
            patch("models.notebook.MAX_NOTEBOOKS", 2),
            patch("models.notebook.k8s.check_quota_headroom", return_value=None),
            patch("models.notebook.k8s.create_notebook_pod") as mock_create,
            patch("models.notebook.k8s.create_service"),
            patch("models.notebook.caddy.add_proxy_route", return_value="route-id"),
        ):
            Notebook.start(self._make_notebook())

            mock_create.assert_called_once()


class TestNotebookStartTierAndGpu:
    """Tests for tier selection, GPU attachment, and invalid tier handling in Notebook.start()."""

    _MOCK_RESOURCES: ClassVar[dict] = {
        "requests": {"cpu": "200m", "memory": "512Mi"},
        "limits": {"cpu": "2", "memory": "4Gi"},
    }

    def _make_notebook(self) -> MagicMock:
        nb = MagicMock()
        nb.experiment_id = "exp-test"
        nb.token = "test-token"
        return nb

    def test_default_tier_uses_small(self) -> None:
        """start() with no tier argument defaults to NotebookTier.SMALL."""
        resources = self._MOCK_RESOURCES
        with (
            patch("models.notebook.k8s.count_notebook_pods", return_value=0),
            patch("models.notebook.MAX_NOTEBOOKS", 2),
            patch("models.notebook.k8s.check_quota_headroom", return_value=None),
            patch("models.notebook.get_tier_resources", return_value=resources) as mock_tier_res,
            patch("models.notebook.k8s.create_notebook_pod"),
            patch("models.notebook.k8s.create_service"),
            patch("models.notebook.caddy.add_proxy_route", return_value="route-id"),
        ):
            Notebook.start(self._make_notebook())
            mock_tier_res.assert_called_once_with(NotebookTier.SMALL)

    def test_selected_tier_scales_resources(self) -> None:
        """start() passes the requested tier to get_tier_resources."""
        resources = self._MOCK_RESOURCES
        with (
            patch("models.notebook.k8s.count_notebook_pods", return_value=0),
            patch("models.notebook.MAX_NOTEBOOKS", 2),
            patch("models.notebook.k8s.check_quota_headroom", return_value=None),
            patch("models.notebook.get_tier_resources", return_value=resources) as mock_tier_res,
            patch("models.notebook.k8s.create_notebook_pod"),
            patch("models.notebook.k8s.create_service"),
            patch("models.notebook.caddy.add_proxy_route", return_value="route-id"),
        ):
            Notebook.start(self._make_notebook(), tier=NotebookTier.MEDIUM)
            mock_tier_res.assert_called_once_with(NotebookTier.MEDIUM)

    def test_gpu_passed_to_create_pod(self) -> None:
        """start() with gpu=True forwards gpu=True to create_notebook_pod."""
        resources = self._MOCK_RESOURCES
        with (
            patch("models.notebook.k8s.count_notebook_pods", return_value=0),
            patch("models.notebook.MAX_NOTEBOOKS", 2),
            patch("models.notebook.GPU_TYPE", "nvidia.com/gpu"),
            patch("models.notebook.k8s.check_quota_headroom", return_value=None),
            patch("models.notebook.get_tier_resources", return_value=resources),
            patch("models.notebook.k8s.create_notebook_pod") as mock_create,
            patch("models.notebook.k8s.create_service"),
            patch("models.notebook.caddy.add_proxy_route", return_value="route-id"),
        ):
            Notebook.start(self._make_notebook(), gpu=True)
            assert mock_create.call_args.kwargs["gpu"] is True

    def test_invalid_tier_raises_bad_request(self) -> None:
        """start() with an unrecognized tier string raises BadRequest without creating a pod."""
        with patch("models.notebook.k8s.create_notebook_pod") as mock_create:
            with pytest.raises(BadRequest):
                Notebook.start(self._make_notebook(), tier="99x")  # type: ignore
            mock_create.assert_not_called()


class TestCreateNotebookPodLifecycleFlags:
    """Verify that create_notebook_pod() injects idle-culling flags and MY_POD_NAME into the pod spec."""

    def test_lifecycle_flags_in_pod_spec(self) -> None:
        """create_notebook_pod() must include cull_idle_timeout, shutdown_no_activity_timeout, and MY_POD_NAME."""
        mock_core = MagicMock()
        with (
            patch("clients.k8s.ping_resource", return_value=False),
            patch("clients.k8s.get_core_v1", return_value=mock_core),
        ):
            create_notebook_pod(
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
