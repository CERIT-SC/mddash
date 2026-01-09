"""
Integration tests for experiment API routes.

Tests the full request/response cycle with mocked external dependencies.
"""

import json
from http import HTTPStatus
from pathlib import Path
from unittest.mock import MagicMock, patch

from flask.testing import FlaskClient
from sqlalchemy.orm import Session


class TestListExperiments:
    """Tests for GET /api/experiments."""

    def test_returns_empty_list_initially(self, client: FlaskClient) -> None:
        """Should return empty list when no experiments exist."""
        response = client.get("/dash/api/experiments")

        assert response.status_code == HTTPStatus.OK
        data = json.loads(response.data)
        assert data["success"] is True
        assert data["data"] == []

    def test_returns_experiments(self, client: FlaskClient, db_session: Session) -> None:
        """Should return list of all experiments."""
        from models import Experiment, Notebook

        # Create test experiment directly in DB
        exp = Experiment()
        exp.id = "testx"
        exp.name = "Test Experiment"
        exp.source_message = "Test"
        db_session.add(exp)
        db_session.flush()

        notebook = Notebook()
        notebook.experiment_id = "testx"
        db_session.add(notebook)
        db_session.commit()

        response = client.get("/dash/api/experiments")

        assert response.status_code == HTTPStatus.OK
        data = json.loads(response.data)
        assert len(data["data"]) == 1
        assert data["data"][0]["id"] == "testx"
        assert data["data"][0]["name"] == "Test Experiment"


class TestGetExperiment:
    """Tests for GET /api/experiments/<id>."""

    def test_returns_experiment_by_id(self, client: FlaskClient, db_session: Session) -> None:
        """Should return experiment details for valid ID."""
        from models import Experiment, Notebook

        exp = Experiment()
        exp.id = "abcde"
        exp.name = "My Experiment"
        exp.source_message = "Created for test"
        db_session.add(exp)
        db_session.flush()

        notebook = Notebook()
        notebook.experiment_id = "abcde"
        db_session.add(notebook)
        db_session.commit()

        response = client.get("/dash/api/experiments/abcde")

        assert response.status_code == HTTPStatus.OK
        data = json.loads(response.data)
        assert data["data"]["id"] == "abcde"
        assert data["data"]["name"] == "My Experiment"

    def test_returns_404_for_missing_experiment(self, client: FlaskClient) -> None:
        """Should return 404 for non-existent experiment ID."""
        response = client.get("/dash/api/experiments/zzzzz")

        assert response.status_code == HTTPStatus.NOT_FOUND


class TestCreateExperiment:
    """Tests for POST /api/experiments."""

    def test_create_from_pdb_success(self, client: FlaskClient, sample_pdb_content: bytes, tmp_path: Path) -> None:
        """Should create experiment from valid PDB ID."""
        with patch("models.experiment.requests.get") as mock_get, patch("models.experiment.DATA_DIR", tmp_path):
            # Mock successful PDB download
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.content = sample_pdb_content
            mock_get.return_value = mock_response

            response = client.post(
                "/dash/api/experiments",
                data={
                    "type": "pdb",
                    "experiment-name": "Test PDB Experiment",
                    "pdb-id": "1ABC",
                },
            )

            assert response.status_code == HTTPStatus.CREATED
            data = json.loads(response.data)
            assert data["success"] is True
            assert data["data"]["name"] == "Test PDB Experiment"
            assert len(data["data"]["id"]) == 5

    def test_create_from_pdb_not_found(self, client: FlaskClient, tmp_path: Path) -> None:
        """Should return 404 when PDB ID doesn't exist."""
        with patch("models.experiment.requests.get") as mock_get, patch("models.experiment.DATA_DIR", tmp_path):
            mock_response = MagicMock()
            mock_response.status_code = 404
            mock_get.return_value = mock_response

            response = client.post(
                "/dash/api/experiments",
                data={
                    "type": "pdb",
                    "experiment-name": "Invalid PDB",
                    "pdb-id": "XXXX",
                },
            )

            assert response.status_code == HTTPStatus.NOT_FOUND

    def test_create_invalid_type(self, client: FlaskClient) -> None:
        """Should return 400 for invalid experiment type."""
        response = client.post(
            "/dash/api/experiments",
            data={
                "type": "invalid",
                "experiment-name": "Test",
            },
        )

        assert response.status_code == HTTPStatus.BAD_REQUEST


class TestEditExperiment:
    """Tests for PATCH /api/experiments/<id>."""

    def test_update_experiment_name(self, client: FlaskClient, db_session: Session) -> None:
        """Should update experiment name."""
        from models import Experiment, Notebook

        exp = Experiment()
        exp.id = "editx"
        exp.name = "Original Name"
        exp.source_message = "Test"
        db_session.add(exp)
        db_session.flush()

        notebook = Notebook()
        notebook.experiment_id = "editx"
        db_session.add(notebook)
        db_session.commit()

        response = client.patch(
            "/dash/api/experiments/editx",
            json={"name": "Updated Name"},
            content_type="application/json",
        )

        assert response.status_code == HTTPStatus.OK
        data = json.loads(response.data)
        assert data["data"]["name"] == "Updated Name"

    def test_update_nonexistent_experiment(self, client: FlaskClient) -> None:
        """Should return 404 when updating non-existent experiment."""
        response = client.patch(
            "/dash/api/experiments/nope1",
            json={"name": "New Name"},
            content_type="application/json",
        )

        assert response.status_code == HTTPStatus.NOT_FOUND

    def test_update_with_no_data(self, client: FlaskClient, db_session: Session) -> None:
        """Should return 400 when no data provided."""
        from models import Experiment, Notebook

        exp = Experiment()
        exp.id = "nodta"
        exp.name = "Test"
        exp.source_message = "Test"
        db_session.add(exp)
        db_session.flush()

        notebook = Notebook()
        notebook.experiment_id = "nodta"
        db_session.add(notebook)
        db_session.commit()

        response = client.patch(
            "/dash/api/experiments/nodta",
            json={},
            content_type="application/json",
        )

        assert response.status_code == HTTPStatus.BAD_REQUEST


class TestDeleteExperiment:
    """Tests for DELETE /api/experiments/<id>."""

    def test_delete_experiment(self, client: FlaskClient, db_session: Session, tmp_path: Path) -> None:
        """Should delete experiment and return 204."""
        from models import Experiment, Notebook

        # Create experiment directory
        exp_dir = tmp_path / "delme"
        exp_dir.mkdir()

        with patch("models.experiment.DATA_DIR", tmp_path):
            exp = Experiment()
            exp.id = "delme"
            exp.name = "To Delete"
            exp.source_message = "Test"
            db_session.add(exp)
            db_session.flush()

            notebook = Notebook()
            notebook.experiment_id = "delme"
            db_session.add(notebook)
            db_session.commit()

            response = client.delete("/dash/api/experiments/delme")

            assert response.status_code == HTTPStatus.NO_CONTENT

    def test_delete_nonexistent_experiment(self, client: FlaskClient) -> None:
        """Should return 404 when deleting non-existent experiment."""
        response = client.delete("/dash/api/experiments/nope2")

        assert response.status_code == HTTPStatus.NOT_FOUND
