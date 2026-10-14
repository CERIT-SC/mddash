"""Integration tests for the health endpoint."""

from http import HTTPStatus

from httpx import AsyncClient


class TestHealthEndpoint:
    """Tests for the /health endpoint."""

    async def test_health_returns_ok(self, client: AsyncClient) -> None:
        """Health endpoint should return 200 OK."""
        response = await client.get("/dash/api/health")

        assert response.status_code == HTTPStatus.OK
