"""Unit tests for archive/restore routes."""

from unittest.mock import Mock, patch

import pytest  # ruff:ignore[unused-import]
from flask.testing import FlaskClient


class TestArchiveRoute:
    def test_conflicts_surface_as_409_problem(self, client: FlaskClient) -> None:
        from werkzeug.exceptions import Conflict

        with patch("models.Experiment.query") as mock_query:
            experiment = Mock()
            experiment.archive.side_effect = Conflict("live jobs running")
            mock_query.get_or_404.return_value = experiment
            response = client.post("/dash/api/experiments/abcde/archive")

        assert response.status_code == 409
        assert response.content_type == "application/problem+json"
        assert response.get_json()["detail"] == "live jobs running"

    def test_success_returns_202(self, client: FlaskClient) -> None:
        with patch("models.Experiment.query") as mock_query:
            experiment = Mock()
            experiment.archive.return_value = "attempt-1"
            mock_query.get_or_404.return_value = experiment
            response = client.post("/dash/api/experiments/abcde/archive")

        assert response.status_code == 202
        assert response.get_json()["attempt_id"] == "attempt-1"


class TestRestoreRoute:
    def test_success_returns_202(self, client: FlaskClient) -> None:
        with patch("models.Experiment.query") as mock_query:
            experiment = Mock()
            experiment.restore.return_value = "attempt-2"
            mock_query.get_or_404.return_value = experiment
            response = client.post("/dash/api/experiments/abcde/restore")

        assert response.status_code == 202
        assert response.get_json()["attempt_id"] == "attempt-2"


class TestArchiveStatusRoute:
    def test_returns_status_doc(self, client: FlaskClient) -> None:
        with patch("models.Experiment.query") as mock_query:
            experiment = Mock()
            experiment.get_archive_status.return_value = {
                "experiment_id": "abcde",
                "archive_state": "archiving",
                "attempt_id": "a1",
                "direction": "archive",
                "reason": None,
            }
            mock_query.get_or_404.return_value = experiment
            response = client.get("/dash/api/experiments/abcde/archive/status")

        assert response.status_code == 200
        body = response.get_json()
        assert body["archive_state"] == "archiving"
        assert body["attempt_id"] == "a1"
