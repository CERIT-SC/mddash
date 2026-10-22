"""Integration tests for the metrics endpoint."""

from http import HTTPStatus

from httpx import AsyncClient


class TestMetricsEndpoint:
    """Tests for GET /api/metrics."""

    async def test_returns_storage_and_uptime(self, client: AsyncClient) -> None:
        """Should return flat storage used/limit and a non-negative server uptime."""
        response = await client.get("/dash/api/metrics")

        assert response.status_code == HTTPStatus.OK
        data = response.json()
        # storage_used_bytes is nullable until the du monitor records a measurement
        assert data["storage_used_bytes"] is None or isinstance(data["storage_used_bytes"], int)
        assert data["storage_limit_bytes"] is None or isinstance(data["storage_limit_bytes"], int)
        assert isinstance(data["uptime_seconds"], int)
        assert data["uptime_seconds"] >= 0
