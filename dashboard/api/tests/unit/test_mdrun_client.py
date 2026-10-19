"""Unit tests for the MDRun HTTP client."""

from http import HTTPStatus

import httpx
import pytest
import respx
from clients import mdrun
from core.config import MDRUN_API_URL


class TestStopJob:
    """POST /stop treats 404 as success (job already gone), like the delete calls."""

    async def test_204_is_plain_success(self, http_mock: respx.MockRouter) -> None:
        route = http_mock.post(f"{MDRUN_API_URL}/jobs/gmx/job-1/stop").mock(return_value=httpx.Response(204))

        await mdrun.stop_job("job-1", "gmx")

        assert route.call_count == 1

    async def test_404_with_gone_job_is_noop(self, http_mock: respx.MockRouter) -> None:
        http_mock.post(f"{MDRUN_API_URL}/jobs/gmx/job-2/stop").mock(return_value=httpx.Response(404))

        await mdrun.stop_job("job-2", "gmx")

    async def test_amber_route(self, http_mock: respx.MockRouter) -> None:
        route = http_mock.post(f"{MDRUN_API_URL}/jobs/amber/job-4/stop").mock(return_value=httpx.Response(204))

        await mdrun.stop_job("job-4", "amber")

        assert route.call_count == 1

    async def test_http_error_propagates_with_upstream_detail(self, http_mock: respx.MockRouter) -> None:
        http_mock.post(f"{MDRUN_API_URL}/jobs/gmx/job-5/stop").mock(
            return_value=httpx.Response(HTTPStatus.INTERNAL_SERVER_ERROR, json={"detail": "boom"})
        )

        with pytest.raises(httpx.HTTPStatusError, match="boom"):
            await mdrun.stop_job("job-5", "gmx")


class TestJobCalls:
    """Create/get/delete wrap the JSON resource API."""

    async def test_create_gmx_job_posts_compute_settings(self, http_mock: respx.MockRouter) -> None:
        route = http_mock.post(f"{MDRUN_API_URL}/jobs/gmx").mock(
            return_value=httpx.Response(201, json={"id": "j1", "status": "PENDING"})
        )

        job = await mdrun.create_gmx_job("abcde", "md.tpr", "bucket", "cpu", "gpu", 2, 4, "-v")

        assert job == {"id": "j1", "status": "PENDING"}
        body = route.calls.last.request.read()
        assert b'"pme":"cpu"' in body
        assert b'"extra_args":"-v"' in body

    async def test_delete_treats_404_as_deleted(self, http_mock: respx.MockRouter) -> None:
        http_mock.delete(f"{MDRUN_API_URL}/jobs/amber/gone").mock(return_value=httpx.Response(404))

        await mdrun.delete_amber_job("gone")

    async def test_get_raises_on_error(self, http_mock: respx.MockRouter) -> None:
        http_mock.get(f"{MDRUN_API_URL}/jobs/gmx/j1").mock(return_value=httpx.Response(503, text="down"))

        with pytest.raises(httpx.HTTPStatusError, match="down"):
            await mdrun.get_gmx_job("j1")
