"""Integration tests for the health endpoint."""

from http import HTTPStatus

from flask.testing import FlaskClient


class TestHealthEndpoint:
    """Tests for the /health endpoint."""

    def test_health_returns_ok(self, client: FlaskClient) -> None:
        """Health endpoint should return 200 OK."""
        response = client.get("/dash/api/health")

        assert response.status_code == HTTPStatus.OK
