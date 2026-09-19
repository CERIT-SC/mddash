"""Unit tests for the MDRun HTTP client's stop endpoint handling."""

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
    """POST /stop treats 404 as success (job already gone), like the delete calls."""

    def test_204_is_plain_success(self, mocker: MockerFixture) -> None:
        post = mocker.patch("requests.post", return_value=_response(HTTPStatus.NO_CONTENT))

        mdrun.stop_job("job-1", "gmx")

        post.assert_called_once()
        assert post.call_args.args[0].endswith("/jobs/gmx/job-1/stop")

    def test_404_with_gone_job_is_noop(self, mocker: MockerFixture) -> None:
        mocker.patch("requests.post", return_value=_response(HTTPStatus.NOT_FOUND))

        mdrun.stop_job("job-2", "gmx")

    def test_amber_route(self, mocker: MockerFixture) -> None:
        post = mocker.patch("requests.post", return_value=_response(HTTPStatus.NO_CONTENT))

        mdrun.stop_job("job-4", "amber")

        assert post.call_args.args[0].endswith("/jobs/amber/job-4/stop")

    def test_http_error_propagates(self, mocker: MockerFixture) -> None:
        mocker.patch("requests.post", return_value=_response(HTTPStatus.INTERNAL_SERVER_ERROR, {"detail": "boom"}))

        with pytest.raises(requests.HTTPError):
            mdrun.stop_job("job-5", "gmx")
