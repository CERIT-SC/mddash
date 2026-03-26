"""Unit tests for Notebook.start() quota enforcement."""

from unittest.mock import MagicMock, patch

import pytest
from enums import NotebookTier
from models.notebook import Notebook
from werkzeug.exceptions import BadRequest, Forbidden


class TestNotebookStartQuotaCheck:
    """Tests for the concurrent-notebook and quota-headroom guards in Notebook.start()."""

    def _make_notebook(self) -> MagicMock:
        nb = MagicMock()
        nb.experiment_id = "exp-test"
        nb.token = "test-token"
        return nb

    def test_raises_forbidden_when_concurrent_limit_reached(self) -> None:
        """start() must raise Forbidden without creating a pod when notebook count is at the limit."""
        with (
            patch("models.notebook.k8s.count_notebook_pods", return_value=2),
            patch("models.notebook.MAX_NOTEBOOKS", 2),
            patch("models.notebook.k8s.create_notebook_pod") as mock_create,
        ):
            with pytest.raises(Forbidden):
                Notebook.start(self._make_notebook())

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

    _MOCK_RESOURCES: dict = {
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
            patch("models.notebook.get_tier_resources", return_value=(resources, resources)) as mock_tier_res,
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
            patch("models.notebook.get_tier_resources", return_value=(resources, resources)) as mock_tier_res,
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
            patch("models.notebook.k8s.check_quota_headroom", return_value=None),
            patch("models.notebook.get_tier_resources", return_value=(resources, resources)),
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
                Notebook.start(self._make_notebook(), tier="99x")
            mock_create.assert_not_called()
