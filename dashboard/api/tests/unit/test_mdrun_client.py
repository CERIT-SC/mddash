"""Unit tests for the MDRun HTTP client — focused on the stop endpoint's 404 handling."""

from http import HTTPStatus
from unittest.mock import MagicMock

import pytest
import requests
from clients import mdrun
from pytest_mock import MockerFixture


def _response(status_code: int, json_data: dict | None = None) -> MagicMock:
    response = MagicMock()
    response.status_code = status_code
    response.ok = 200 <= status_code < 300
    response.json.return_value = json_data or {}
    response.text = str(json_data or {})
    return response


class TestStopJob:
    """POST /stop 404 conflates 'job gone' with 'route missing' — only the former is a no-op."""

    def test_204_is_plain_success(self, mocker: MockerFixture) -> None:
        post = mocker.patch("requests.post", return_value=_response(HTTPStatus.NO_CONTENT))
        get = mocker.patch("requests.get")

        mdrun.stop_gmx_job("job-1")

        post.assert_called_once()
        assert post.call_args.args[0].endswith("/jobs/gmx/job-1/stop")
        get.assert_not_called()

    def test_404_with_gone_job_is_noop(self, mocker: MockerFixture) -> None:
        """A real 404 (job already gone) is verified with a GET that also 404s."""
        mocker.patch("requests.post", return_value=_response(HTTPStatus.NOT_FOUND))
        mocker.patch("requests.get", return_value=_response(HTTPStatus.NOT_FOUND))

        mdrun.stop_gmx_job("job-2")  # no exception

    def test_404_with_existing_job_raises(self, mocker: MockerFixture) -> None:
        """404 from an MDRun that lacks the stop route (job still exists) must not pass silently."""
        mocker.patch("requests.post", return_value=_response(HTTPStatus.NOT_FOUND))
        mocker.patch("requests.get", return_value=_response(HTTPStatus.OK, {"id": "job-3", "status": "running"}))

        with pytest.raises(requests.HTTPError, match="may not support stopping"):
            mdrun.stop_gmx_job("job-3")

    def test_amber_route(self, mocker: MockerFixture) -> None:
        post = mocker.patch("requests.post", return_value=_response(HTTPStatus.NO_CONTENT))
        mocker.patch("requests.get")

        mdrun.stop_amber_job("job-4")

        assert post.call_args.args[0].endswith("/jobs/amber/job-4/stop")

    def test_http_error_propagates(self, mocker: MockerFixture) -> None:
        mocker.patch("requests.post", return_value=_response(HTTPStatus.INTERNAL_SERVER_ERROR, {"detail": "boom"}))
        mocker.patch("requests.get")

        with pytest.raises(requests.HTTPError):
            mdrun.stop_gmx_job("job-5")
