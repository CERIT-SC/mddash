"""Unit tests for the MetaDump API client."""

from collections.abc import Iterator
from pathlib import Path
from unittest.mock import AsyncMock, patch

import clients.metadump as metadump_module
import httpx
import pytest
import respx
from clients.metadump import extract_metadata, extract_metadata_bulk
from core.errors import InternalServerError

TEST_URL = "http://test-metadump"

_SAMPLE_METADATA = {
    "forcefield": "charmm36",
    "water_model": "tip3p",
    "nsteps": 100000,
    "dt": 0.002,
}


@pytest.fixture(autouse=True)
def _metadump() -> Iterator[None]:
    with patch("clients.metadump.METADUMP_API_URL", TEST_URL), patch("clients.metadump.asyncio.sleep", AsyncMock()):
        yield


@pytest.fixture
def tpr(tmp_path: Path) -> Path:
    path = tmp_path / "md.tpr"
    path.write_bytes(b"fake tpr content")
    return path


def _submit(http_mock: respx.MockRouter, *uuids: str) -> respx.Route:
    return http_mock.post(f"{TEST_URL}/api/annotate").mock(
        side_effect=[httpx.Response(200, json={"uuid": uuid, "pin": "123456"}) for uuid in uuids]
    )


def _statuses(http_mock: respx.MockRouter, uuid: str, *statuses: str) -> respx.Route:
    return http_mock.get(f"{TEST_URL}/api/annotate/{uuid}").mock(
        side_effect=[httpx.Response(200, json={"uuid": uuid, "status": s}) for s in statuses]
    )


def _results(http_mock: respx.MockRouter, uuid: str, metadata: dict | None = None) -> respx.Route:
    return http_mock.get(f"{TEST_URL}/api/annotate/{uuid}/results").mock(
        return_value=httpx.Response(200, json={"uuid": uuid, "metadata": metadata or _SAMPLE_METADATA})
    )


def _delete(http_mock: respx.MockRouter) -> respx.Route:
    return http_mock.delete(url__regex=rf"{TEST_URL}/api/annotate/.*").mock(
        return_value=httpx.Response(200, json={"message": "deleted"})
    )


class TestExtractMetadataBulk:
    """Tests for extract_metadata_bulk."""

    async def test_single_tpr_happy_path(self, http_mock: respx.MockRouter, tpr: Path) -> None:
        """POST → uuid/pin, GET status → completed, GET results, DELETE all succeed."""
        _submit(http_mock, "uuid-1")
        _results(http_mock, "uuid-1")
        _statuses(http_mock, "uuid-1", "completed")
        _delete(http_mock)

        results = await extract_metadata_bulk([tpr])

        assert len(results) == 1
        assert results[0]["metadata"] == _SAMPLE_METADATA

    async def test_single_tpr_calls_delete_for_cleanup(self, http_mock: respx.MockRouter, tpr: Path) -> None:
        """DELETE must be called even when results are fetched successfully."""
        _submit(http_mock, "uuid-1")
        _results(http_mock, "uuid-1")
        _statuses(http_mock, "uuid-1", "completed")
        delete = _delete(http_mock)

        await extract_metadata_bulk([tpr])

        assert delete.call_count == 1
        assert "uuid-1" in str(delete.calls.last.request.url)
        assert delete.calls.last.request.url.params["pin"] == "123456"

    async def test_multiple_tprs_results_in_input_order(self, http_mock: respx.MockRouter, tmp_path: Path) -> None:
        """Results must be returned in the same order as the input paths."""
        tpr_a = tmp_path / "a.tpr"
        tpr_b = tmp_path / "b.tpr"
        tpr_a.write_bytes(b"tpr a")
        tpr_b.write_bytes(b"tpr b")
        _submit(http_mock, "uuid-a", "uuid-b")
        _results(http_mock, "uuid-a", {"nsteps": 1000})
        _results(http_mock, "uuid-b", {"nsteps": 2000})
        _statuses(http_mock, "uuid-a", "completed")
        _statuses(http_mock, "uuid-b", "completed")
        _delete(http_mock)

        results = await extract_metadata_bulk([tpr_a, tpr_b])

        assert [r["metadata"] for r in results] == [{"nsteps": 1000}, {"nsteps": 2000}]

    async def test_empty_input_returns_empty_list(self, http_mock: respx.MockRouter) -> None:
        """Empty input list should return empty list without any HTTP calls."""
        assert await extract_metadata_bulk([]) == []
        assert not http_mock.calls

    async def test_missing_env_var_returns_empty_list(self, http_mock: respx.MockRouter, tpr: Path) -> None:
        """When METADUMP_API_URL is None, return empty list without HTTP calls."""
        with patch("clients.metadump.METADUMP_API_URL", None):
            assert await extract_metadata_bulk([tpr]) == []
        assert not http_mock.calls

    async def test_timeout_raises_and_still_cleans_up(self, http_mock: respx.MockRouter, tpr: Path) -> None:
        """After MAX_POLLS with no completion, raise InternalServerError; DELETE still runs."""
        _submit(http_mock, "uuid-1")
        _statuses(http_mock, "uuid-1", *["pending"] * metadump_module.MAX_POLLS)
        delete = _delete(http_mock)

        with pytest.raises(InternalServerError) as exc_info:
            await extract_metadata_bulk([tpr])

        assert "timed out" in exc_info.value.description.lower()
        assert delete.call_count == 1

    async def test_upload_http_error_raises_internal_server_error(self, http_mock: respx.MockRouter, tpr: Path) -> None:
        """When POST returns a non-2xx response, raise InternalServerError."""
        http_mock.post(f"{TEST_URL}/api/annotate").mock(
            return_value=httpx.Response(500, json={"detail": "Internal Server Error"})
        )

        with pytest.raises(InternalServerError) as exc_info:
            await extract_metadata_bulk([tpr])

        assert "500" in exc_info.value.description

    async def test_upload_failure_cleans_up_already_submitted_jobs(
        self, http_mock: respx.MockRouter, tmp_path: Path
    ) -> None:
        """A failing second upload must not leak the first remote job."""
        tpr_a = tmp_path / "a.tpr"
        tpr_b = tmp_path / "b.tpr"
        tpr_a.write_bytes(b"tpr a")
        tpr_b.write_bytes(b"tpr b")
        http_mock.post(f"{TEST_URL}/api/annotate").mock(
            side_effect=[httpx.Response(200, json={"uuid": "uuid-a", "pin": "1"}), httpx.Response(500)]
        )
        delete = _delete(http_mock)

        with pytest.raises(InternalServerError):
            await extract_metadata_bulk([tpr_a, tpr_b])

        assert delete.call_count == 1
        assert "uuid-a" in str(delete.calls.last.request.url)

    async def test_error_status_raises_internal_server_error(self, http_mock: respx.MockRouter, tpr: Path) -> None:
        """When a job enters 'error' status, raise InternalServerError."""
        _submit(http_mock, "uuid-1")
        _statuses(http_mock, "uuid-1", "error")
        _delete(http_mock)

        with pytest.raises(InternalServerError) as exc_info:
            await extract_metadata_bulk([tpr])

        assert "error status" in exc_info.value.description.lower()

    async def test_running_status_continues_polling(self, http_mock: respx.MockRouter, tpr: Path) -> None:
        """A 'running' status should not raise — polling should continue."""
        _submit(http_mock, "uuid-1")
        _results(http_mock, "uuid-1")
        _statuses(http_mock, "uuid-1", "running", "completed")
        _delete(http_mock)

        assert len(await extract_metadata_bulk([tpr])) == 1


class TestExtractMetadata:
    """Tests for the single-file extract_metadata convenience wrapper."""

    async def test_returns_single_result(self, http_mock: respx.MockRouter, tpr: Path) -> None:
        """Should unwrap the list result and return a single dict."""
        _submit(http_mock, "uuid-1")
        _results(http_mock, "uuid-1")
        _statuses(http_mock, "uuid-1", "completed")
        _delete(http_mock)

        result = await extract_metadata(tpr)

        assert result["metadata"] == _SAMPLE_METADATA

    def test_max_polls_constant(self) -> None:
        """MAX_POLLS should equal TIMEOUT_SEC // POLL_INTERVAL_SEC."""
        assert metadump_module.MAX_POLLS == metadump_module.TIMEOUT_SEC // metadump_module.POLL_INTERVAL_SEC
        assert metadump_module.MAX_POLLS == 30
