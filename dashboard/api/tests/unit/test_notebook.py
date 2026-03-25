"""Unit tests for Notebook.start() quota enforcement."""

from unittest.mock import MagicMock, patch

import pytest
from models.notebook import Notebook
from werkzeug.exceptions import Forbidden


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
