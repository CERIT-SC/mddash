"""Integration tests for the notebook modules catalog endpoint."""

import json
from http import HTTPStatus

from flask.testing import FlaskClient

MIN_MODULE_COUNT = 2


class TestNotebookModulesEndpoint:
    """Tests for GET /api/notebook-modules."""

    def test_returns_display_metadata_without_internal_paths(self, client: FlaskClient) -> None:
        """Should return modules with display fields, no internal paths/URLs, JSON-serializable."""
        response = client.get("/dash/api/notebook-modules")

        assert response.status_code == HTTPStatus.OK
        data = json.loads(response.data)
        assert isinstance(data, list)
        assert len(data) >= MIN_MODULE_COUNT

        ids = {m["id"] for m in data}
        assert "gromacs-protein" in ids

        for module in data:
            assert "id" in module
            assert "name" in module
            assert "engine" in module
            assert module["engine"] in {"GMX", "AMBER"}
            assert "author" in module
            assert module["category"] in {"protein", "membrane-protein"}
            assert "path" not in module
            assert "repository" not in module
            assert "url" not in module

        json.dumps(data)
