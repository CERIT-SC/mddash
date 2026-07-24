"""Integration tests for the notebook modules catalog endpoint."""

import json
from http import HTTPStatus

from flask.testing import FlaskClient

MIN_MODULE_COUNT = 2


class TestNotebookModulesEndpoint:
    """Tests for GET /api/notebook-modules."""

    def test_returns_catalog_display_metadata(self, client: FlaskClient) -> None:
        """Should return modules with display fields and no internal paths."""
        response = client.get("/dash/api/notebook-modules")

        assert response.status_code == HTTPStatus.OK
        data = json.loads(response.data)
        assert isinstance(data, list)
        assert len(data) >= MIN_MODULE_COUNT

        ids = {m["id"] for m in data}
        assert "gromacs-protein" in ids
        assert "amber-protein" in ids

    def test_response_excludes_internal_paths(self, client: FlaskClient) -> None:
        """The catalog response must not expose internal Git paths or repository URLs."""
        response = client.get("/dash/api/notebook-modules")

        data = json.loads(response.data)
        for module in data:
            assert "path" not in module
            assert "repository" not in module
            assert "url" not in module

    def test_response_includes_required_display_fields(self, client: FlaskClient) -> None:
        """Each module entry should include id, name, engine, and description."""
        response = client.get("/dash/api/notebook-modules")

        data = json.loads(response.data)
        for module in data:
            assert "id" in module
            assert "name" in module
            assert "engine" in module
            assert module["engine"] in {"GMX", "AMBER"}

    def test_response_is_json_serializable(self, client: FlaskClient) -> None:
        """The catalog response should be JSON-serializable as-is."""
        response = client.get("/dash/api/notebook-modules")

        data = json.loads(response.data)
        json.dumps(data)
