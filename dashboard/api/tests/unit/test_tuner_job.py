"""Unit tests for TunerJob status handling."""

from http import HTTPStatus
from typing import Any
from unittest.mock import AsyncMock, Mock, patch

import httpx
import pytest
from clients import Clients
from core.cache import tuner_last_known_status
from core.enums import Engine, JobStatus
from core.errors import ApiError
from modules.jobs.tuner.service import TunerService
from modules.models import Experiment, TunerJob

EXPECTED_PERFORMANCE = 42.0
JOB_ID = "4f6cf7a7-4120-4f6c-87fe-61313b1684df"


def _http_error(status: int, message: str = "error") -> httpx.HTTPStatusError:
    """Build the error the tuner client raises for an upstream error status."""
    return httpx.HTTPStatusError(
        message, request=httpx.Request("GET", "http://tuner/x"), response=httpx.Response(status)
    )


def _experiment() -> Experiment:
    return Experiment(id="abcde", name="Test", notebooks_repo="https://example.com/repo", engine=Engine.AMBER)


def _make_tuner_job(*, is_stopped: bool = False) -> TunerJob:
    """Build an AMBER tuner job (transient: refresh never touches the database)."""
    return TunerJob(
        id=JOB_ID,
        experiment=_experiment(),
        simulation_path="production/test.simulation.json",
        nsteps=25000,
        is_stopped=is_stopped,
    )


@pytest.fixture
def service(clients: Clients) -> TunerService:
    """Status refreshes never touch the database."""
    return TunerService(AsyncMock(), clients)


def _poll(clients: Clients, **kwargs: Any) -> Any:
    return patch.object(clients.tuner, "poll_status", AsyncMock(**kwargs))


def _delete(clients: Clients, **kwargs: Any) -> Any:
    return patch.object(clients.tuner, "delete_job", AsyncMock(**kwargs))


class TestTunerJobNotFound:
    """A 404 from the tuner must mark the job gone instead of re-polling forever."""

    async def test_404_marks_job_stopped(self, service: TunerService, clients: Clients) -> None:
        job = _make_tuner_job()

        with (
            _poll(clients, side_effect=_http_error(HTTPStatus.NOT_FOUND)),
            _delete(clients, side_effect=_http_error(404)),
        ):
            await service.refresh(job)

        assert job._status() == {}
        assert job.is_stopped is True

    async def test_404_preserves_last_known_trials(self, service: TunerService, clients: Clients) -> None:
        """Trials from the last known status must be preserved when the job goes missing."""
        job = _make_tuner_job()
        tuner_last_known_status[job.id] = {
            "status": JobStatus.RUNNING,
            "trials": [
                {"id": "t1", "performance": EXPECTED_PERFORMANCE},
                {"id": "t2", "performance": None},
            ],
        }

        with (
            _poll(clients, side_effect=_http_error(HTTPStatus.NOT_FOUND)),
            _delete(clients, side_effect=_http_error(404)),
        ):
            await service.refresh(job)

        assert job.is_stopped is True
        preserved = job.trials
        assert len(preserved) == 1
        assert preserved[0]["performance"] == pytest.approx(EXPECTED_PERFORMANCE)

    async def test_stopped_job_does_not_re_poll(self, service: TunerService, clients: Clients) -> None:
        """Once marked gone, subsequent refreshes must not hit the tuner again."""
        job = _make_tuner_job()

        with _poll(clients, side_effect=_http_error(HTTPStatus.NOT_FOUND)) as mock_poll, _delete(clients):
            await service.refresh(job)
            await service.refresh(job)
            await service.refresh(job)

        assert mock_poll.call_count == 1

    async def test_non_404_error_does_not_mark_stopped(self, service: TunerService, clients: Clients) -> None:
        """A 5xx (non-404) error must not permanently mark the job stopped."""
        job = _make_tuner_job()

        with _poll(clients, side_effect=_http_error(HTTPStatus.INTERNAL_SERVER_ERROR, "boom")):
            await service.refresh(job)

        assert job._status() == {}
        assert job.is_stopped is False

    async def test_successful_poll_does_not_mark_stopped(self, service: TunerService, clients: Clients) -> None:
        job = _make_tuner_job()
        ok_status = {"status": JobStatus.RUNNING, "trials": []}

        with _poll(clients, return_value=ok_status):
            await service.refresh(job)

        assert job._status() == ok_status
        assert job.is_stopped is False

    def test_reading_status_before_refresh_fails_loudly(self) -> None:
        with pytest.raises(RuntimeError, match="read before"):
            _ = _make_tuner_job().tuner_status


class TestTunerJobFinished:
    """A FINISHED job must be persisted dashboard-side and stop polling the tuner."""

    async def test_finished_poll_stops_job_and_preserves_trials(self, service: TunerService, clients: Clients) -> None:
        job = _make_tuner_job()
        finished_status = {
            "status": JobStatus.FINISHED,
            "trials": [
                {"id": "t1", "performance": EXPECTED_PERFORMANCE},
                {"id": "t2", "performance": None},
            ],
        }

        with (
            _poll(clients, side_effect=[finished_status, AssertionError("re-polled")]),
            _delete(clients) as mock_delete,
        ):
            await service.refresh(job)
            await service.refresh(job)

        assert job._status_data == finished_status
        assert job.is_stopped is True
        assert mock_delete.call_count == 1
        preserved = job.trials
        assert len(preserved) == 1
        assert preserved[0]["performance"] == pytest.approx(EXPECTED_PERFORMANCE)


class TestTunerJobErrorStatus:
    """An ERROR status from the tuner must always populate error_message."""

    async def test_error_status_with_message_sets_error_message(self, service: TunerService, clients: Clients) -> None:
        job = _make_tuner_job()
        error_status = {"status": JobStatus.ERROR, "error": "Tuner exploded", "trials": []}

        with _poll(clients, return_value=error_status):
            await service.refresh(job)

        assert job._status() == error_status
        assert job.error_message == "Tuner exploded"

    async def test_error_status_without_message_sets_default_error_message(
        self, service: TunerService, clients: Clients
    ) -> None:
        job = _make_tuner_job()
        error_status = {"status": JobStatus.ERROR, "trials": []}

        with _poll(clients, return_value=error_status):
            await service.refresh(job)

        assert job._status() == error_status
        assert job.error_message == "Tuning job failed on the tuner."


class TestTunerJobStartFailure:
    """A tuner submit failure must surface as a friendly upstream-unavailable error."""

    @pytest.mark.parametrize(
        "exc",
        [
            _http_error(500, "tuner returned 500"),
            httpx.ConnectError("tuner unreachable"),
        ],
        ids=["http-error", "connection-error"],
    )
    async def test_submit_failure_raises_upstream_unavailable(
        self, exc: Exception, service: TunerService, clients: Clients
    ) -> None:
        simulation = Mock()
        simulation.extra_args = ""

        with (
            patch("modules.jobs.tuner.service.get_experiment_or_404", AsyncMock(return_value=_experiment())),
            patch.object(service, "find", AsyncMock(return_value=None)),
            patch("modules.jobs.tuner.service.Simulation.get", return_value=simulation),
            patch.object(clients.tuner, "submit", AsyncMock(side_effect=exc)),
            pytest.raises(ApiError) as exc_info,
        ):
            await service.start("abcde", "production/test.simulation.json", nsteps=1000)

        assert exc_info.value.problem_type == "urn:mddash:upstream-unavailable"
        assert exc_info.value.status_code == HTTPStatus.INTERNAL_SERVER_ERROR
        assert exc_info.value.problem_solution is not None


class TestTunerStatusCoercion:
    """The status dict carries raw JSON strings; tuner_status must still return JobStatus members."""

    async def test_raw_string_status_is_coerced(self, service: TunerService, clients: Clients) -> None:
        job = _make_tuner_job()
        with _poll(clients, return_value={"status": "RUNNING", "trials": []}):
            await service.refresh(job)

        assert job.tuner_status is JobStatus.RUNNING
        assert job.is_live is True

    async def test_unknown_status_string_degrades_to_unknown(self, service: TunerService, clients: Clients) -> None:
        job = _make_tuner_job()
        with _poll(clients, return_value={"status": "FUTURE_STATE", "trials": []}):
            await service.refresh(job)

        assert job.tuner_status is JobStatus.UNKNOWN
        assert job.is_live is True

    def test_stopped_job_is_not_live(self) -> None:
        """A stopped job reports UNKNOWN (from the empty status dict) but is terminal."""
        job = _make_tuner_job(is_stopped=True)

        assert job.tuner_status is JobStatus.UNKNOWN
        assert job.is_live is False
