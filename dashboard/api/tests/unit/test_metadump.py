"""Unit tests for the MetaDump API client."""

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import clients.metadump as metadump_module
import pytest
from clients.metadump import extract_metadata, extract_metadata_bulk
from werkzeug.exceptions import InternalServerError

TEST_URL = "http://test-metadump"

_SAMPLE_METADATA = {
    "forcefield": "charmm36",
    "water_model": "tip3p",
    "nsteps": 100000,
    "dt": 0.002,
}


def _make_response(status_code: int, body: dict) -> MagicMock:
    mock = MagicMock()
    mock.status_code = status_code
    mock.ok = status_code < 400  # ruff:ignore[magic-value-comparison]
    mock.json.return_value = body
    mock.text = json.dumps(body)
    return mock


def _submit_response(uuid: str = "test-uuid-1", pin: str = "123456") -> MagicMock:
    return _make_response(200, {"uuid": uuid, "pin": pin})


def _status_response(uuid: str = "test-uuid-1", status: str = "completed") -> MagicMock:
    return _make_response(200, {"uuid": uuid, "status": status})


def _results_response(uuid: str = "test-uuid-1") -> MagicMock:
    return _make_response(200, {"uuid": uuid, "metadata": _SAMPLE_METADATA})


def _delete_response() -> MagicMock:
    return _make_response(200, {"message": "deleted"})


class TestExtractMetadataBulk:
    """Tests for extract_metadata_bulk."""

    def test_single_tpr_happy_path(self, tmp_path: Path) -> None:
        """POST → uuid/pin, GET status → completed, GET results, DELETE all succeed."""
        tpr = tmp_path / "md.tpr"
        tpr.write_bytes(b"fake tpr content")

        with (
            patch("clients.metadump.METADUMP_API_URL", TEST_URL),
            patch("clients.metadump.time.sleep"),
            patch("requests.post", return_value=_submit_response("uuid-1")),
            patch("requests.get") as mock_get,
            patch("requests.delete", return_value=_delete_response()),
        ):
            mock_get.side_effect = [
                _status_response("uuid-1", "completed"),
                _results_response("uuid-1"),
            ]

            results = extract_metadata_bulk([tpr])

        assert len(results) == 1
        assert results[0]["metadata"] == _SAMPLE_METADATA

    def test_single_tpr_calls_delete_for_cleanup(self, tmp_path: Path) -> None:
        """DELETE must be called even when results are fetched successfully."""
        tpr = tmp_path / "md.tpr"
        tpr.write_bytes(b"fake tpr content")

        with (
            patch("clients.metadump.METADUMP_API_URL", TEST_URL),
            patch("clients.metadump.time.sleep"),
            patch("requests.post", return_value=_submit_response("uuid-1")),
            patch("requests.get") as mock_get,
            patch("requests.delete", return_value=_delete_response()) as mock_delete,
        ):
            mock_get.side_effect = [
                _status_response("uuid-1", "completed"),
                _results_response("uuid-1"),
            ]

            extract_metadata_bulk([tpr])

        mock_delete.assert_called_once()
        call_url = mock_delete.call_args[0][0]
        assert "uuid-1" in call_url

    def test_multiple_tprs_results_in_input_order(self, tmp_path: Path) -> None:
        """Results must be returned in the same order as the input paths."""
        tpr_a = tmp_path / "a.tpr"
        tpr_b = tmp_path / "b.tpr"
        tpr_a.write_bytes(b"tpr a")
        tpr_b.write_bytes(b"tpr b")

        metadata_a = {"nsteps": 1000}
        metadata_b = {"nsteps": 2000}

        with (
            patch("clients.metadump.METADUMP_API_URL", TEST_URL),
            patch("clients.metadump.time.sleep"),
            patch("requests.post") as mock_post,
            patch("requests.get") as mock_get,
            patch("requests.delete", return_value=_delete_response()),
        ):
            mock_post.side_effect = [
                _submit_response("uuid-a"),
                _submit_response("uuid-b"),
            ]

            # First poll: both complete in the same round
            def get_response(url: str, **_kwargs: object) -> object:
                if url.endswith("/results"):
                    uuid = url.split("/")[-2]
                    data = (
                        {"uuid": "uuid-a", "metadata": metadata_a}
                        if uuid == "uuid-a"
                        else {"uuid": "uuid-b", "metadata": metadata_b}
                    )
                    return _make_response(200, data)
                uuid = url.rsplit("/", maxsplit=1)[-1]
                return _status_response(uuid, "completed")

            mock_get.side_effect = get_response

            results = extract_metadata_bulk([tpr_a, tpr_b])

        assert len(results) == 2  # ruff:ignore[magic-value-comparison]
        # Order must match [tpr_a, tpr_b]
        assert results[0]["metadata"] == metadata_a
        assert results[1]["metadata"] == metadata_b

    def test_empty_input_returns_empty_list(self) -> None:
        """Empty input list should return empty list without any HTTP calls."""
        with (
            patch("clients.metadump.METADUMP_API_URL", TEST_URL),
            patch("requests.post") as mock_post,
        ):
            results = extract_metadata_bulk([])

        assert results == []
        mock_post.assert_not_called()

    def test_missing_env_var_returns_empty_list(self, tmp_path: Path) -> None:
        """When METADUMP_API_URL is None, return empty list without HTTP calls."""
        tpr = tmp_path / "md.tpr"
        tpr.write_bytes(b"fake tpr content")

        with (
            patch("clients.metadump.METADUMP_API_URL", None),
            patch("requests.post") as mock_post,
            patch("requests.get") as mock_get,
        ):
            results = extract_metadata_bulk([tpr])

        assert results == []
        mock_post.assert_not_called()
        mock_get.assert_not_called()

    def test_timeout_raises_internal_server_error(self, tmp_path: Path) -> None:
        """After MAX_POLLS with no completion, raise InternalServerError."""
        tpr = tmp_path / "md.tpr"
        tpr.write_bytes(b"fake tpr content")

        pending_response = _status_response("uuid-1", "pending")

        with (
            patch("clients.metadump.METADUMP_API_URL", TEST_URL),
            patch("clients.metadump.time.sleep"),
            patch("requests.post", return_value=_submit_response("uuid-1")),
            patch("requests.get", return_value=pending_response),
            patch("requests.delete", return_value=_delete_response()),
            pytest.raises(InternalServerError) as exc_info,
        ):
            extract_metadata_bulk([tpr])

        assert "timed out" in (exc_info.value.description or "").lower()

    def test_timeout_still_calls_delete(self, tmp_path: Path) -> None:
        """DELETE must be called for cleanup even when timeout is reached."""
        tpr = tmp_path / "md.tpr"
        tpr.write_bytes(b"fake tpr content")

        with (
            patch("clients.metadump.METADUMP_API_URL", TEST_URL),
            patch("clients.metadump.time.sleep"),
            patch("requests.post", return_value=_submit_response("uuid-1")),
            patch("requests.get", return_value=_status_response("uuid-1", "pending")),
            patch("requests.delete", return_value=_delete_response()) as mock_delete,
            pytest.raises(InternalServerError),
        ):
            extract_metadata_bulk([tpr])

        mock_delete.assert_called_once()

    def test_upload_http_error_raises_internal_server_error(self, tmp_path: Path) -> None:
        """When POST returns a non-2xx response, raise InternalServerError."""
        tpr = tmp_path / "md.tpr"
        tpr.write_bytes(b"fake tpr content")

        error_response = _make_response(500, {"detail": "Internal Server Error"})

        with (
            patch("clients.metadump.METADUMP_API_URL", TEST_URL),
            patch("requests.post", return_value=error_response),
            pytest.raises(InternalServerError) as exc_info,
        ):
            extract_metadata_bulk([tpr])

        assert "500" in (exc_info.value.description or "")

    def test_error_status_raises_internal_server_error(self, tmp_path: Path) -> None:
        """When a job enters 'error' status, raise InternalServerError."""
        tpr = tmp_path / "md.tpr"
        tpr.write_bytes(b"fake tpr content")

        with (
            patch("clients.metadump.METADUMP_API_URL", TEST_URL),
            patch("clients.metadump.time.sleep"),
            patch("requests.post", return_value=_submit_response("uuid-1")),
            patch("requests.get", return_value=_status_response("uuid-1", "error")),
            patch("requests.delete", return_value=_delete_response()),
            pytest.raises(InternalServerError) as exc_info,
        ):
            extract_metadata_bulk([tpr])

        assert "error status" in (exc_info.value.description or "").lower()

    def test_running_status_continues_polling(self, tmp_path: Path) -> None:
        """A 'running' status should not raise — polling should continue."""
        tpr = tmp_path / "md.tpr"
        tpr.write_bytes(b"fake tpr content")

        with (
            patch("clients.metadump.METADUMP_API_URL", TEST_URL),
            patch("clients.metadump.time.sleep"),
            patch("requests.post", return_value=_submit_response("uuid-1")),
            patch("requests.get") as mock_get,
            patch("requests.delete", return_value=_delete_response()),
        ):
            mock_get.side_effect = [
                _status_response("uuid-1", "running"),
                _status_response("uuid-1", "completed"),
                _results_response("uuid-1"),
            ]

            results = extract_metadata_bulk([tpr])

        assert len(results) == 1


class TestExtractMetadata:
    """Tests for the single-file extract_metadata convenience wrapper."""

    def test_returns_single_result(self, tmp_path: Path) -> None:
        """Should unwrap the list result and return a single dict."""
        tpr = tmp_path / "md.tpr"
        tpr.write_bytes(b"fake tpr content")

        with (
            patch("clients.metadump.METADUMP_API_URL", TEST_URL),
            patch("clients.metadump.time.sleep"),
            patch("requests.post", return_value=_submit_response("uuid-1")),
            patch("requests.get") as mock_get,
            patch("requests.delete", return_value=_delete_response()),
        ):
            mock_get.side_effect = [
                _status_response("uuid-1", "completed"),
                _results_response("uuid-1"),
            ]

            result = extract_metadata(tpr)

        assert result["metadata"] == _SAMPLE_METADATA

    def test_max_polls_constant(self) -> None:
        """MAX_POLLS should equal TIMEOUT_SEC // POLL_INTERVAL_SEC."""
        assert metadump_module.MAX_POLLS == metadump_module.TIMEOUT_SEC // metadump_module.POLL_INTERVAL_SEC
        assert metadump_module.MAX_POLLS == 30  # ruff:ignore[magic-value-comparison]
