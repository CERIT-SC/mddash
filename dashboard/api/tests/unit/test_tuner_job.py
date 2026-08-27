"""Unit tests for TunerJob status handling."""

from http import HTTPStatus
from unittest.mock import Mock, patch

import pytest
from cache import tuner_last_known_status, tuner_status_cache
from enums import Engine, JobStatus
from flask import Flask
from models import Experiment, TunerJob
from requests import ConnectionError as RequestsConnectionError
from requests import HTTPError
from sqlalchemy.orm import Session

EXPECTED_PERFORMANCE = 42.0
JOB_ID = "4f6cf7a7-4120-4f6c-87fe-61313b1684df"


def _not_found() -> HTTPError:
    """
    Build the HTTPError the tuner client raises on a missing job.

    Returns:
        An HTTPError carrying a 404 response mock.
    """
    return HTTPError("not found", response=Mock(status_code=HTTPStatus.NOT_FOUND))


def _make_experiment(db_session: Session) -> Experiment:
    """
    Create and persist a minimal AMBER experiment.

    Returns:
        The persisted experiment instance.
    """
    experiment = Experiment(
        id="abcde",
        name="Test",
        notebooks_repo="https://example.com/repo",
        engine=Engine.AMBER,
    )
    db_session.add(experiment)
    db_session.flush()
    return experiment


def _make_tuner_job(experiment: Experiment) -> TunerJob:
    """
    Build an unsaved AMBER tuner job for the given experiment.

    Returns:
        A new TunerJob instance bound to the experiment.
    """
    return TunerJob(
        id=JOB_ID,
        experiment_id=experiment.id,
        simulation_path="production/test.simulation.json",
        nsteps=25000,
    )


class TestTunerJobNotFound:
    """A 404 from the tuner must mark the job gone instead of re-polling forever."""

    def setup_method(self) -> None:
        """Clear tuner caches before each test."""
        tuner_status_cache.clear()
        tuner_last_known_status.clear()

    def teardown_method(self) -> None:
        """Clear tuner caches after each test."""
        tuner_status_cache.clear()
        tuner_last_known_status.clear()

    def test_404_marks_job_stopped(self, app: Flask, db_session: Session) -> None:
        """A 404 from the tuner must flip the job to the stopped state."""
        experiment = _make_experiment(db_session)
        job = _make_tuner_job(experiment)
        db_session.add(job)
        db_session.commit()

        with (
            patch("models.tuner_job.tuner.amber_poll_status", side_effect=_not_found()),
            patch("models.tuner_job.tuner.amber_delete_job", side_effect=_not_found()),
        ):
            status = job._status()

        assert status == {}
        assert job.is_stopped is True

    def test_404_preserves_last_known_trials(self, app: Flask, db_session: Session) -> None:
        """Trials from the last known status must be preserved when the job goes missing."""
        experiment = _make_experiment(db_session)
        job = _make_tuner_job(experiment)
        db_session.add(job)
        db_session.commit()

        tuner_last_known_status[job.id] = {
            "status": JobStatus.RUNNING,
            "trials": [
                {"id": "t1", "performance": EXPECTED_PERFORMANCE},
                {"id": "t2", "performance": None},
            ],
        }

        with (
            patch("models.tuner_job.tuner.amber_poll_status", side_effect=_not_found()),
            patch("models.tuner_job.tuner.amber_delete_job", side_effect=_not_found()),
        ):
            job._status()

        assert job.is_stopped is True
        preserved = job.trials
        assert len(preserved) == 1
        assert preserved[0]["performance"] == pytest.approx(EXPECTED_PERFORMANCE)

    def test_stopped_job_does_not_re_poll(self, app: Flask, db_session: Session) -> None:
        """Once marked gone, subsequent status reads must not hit the tuner again."""
        experiment = _make_experiment(db_session)
        job = _make_tuner_job(experiment)
        db_session.add(job)
        db_session.commit()

        with (
            patch("models.tuner_job.tuner.amber_poll_status", side_effect=_not_found()) as mock_poll,
            patch("models.tuner_job.tuner.amber_delete_job", side_effect=_not_found()),
        ):
            job._status()
            job._status()
            job._status()

        assert mock_poll.call_count == 1

    def test_non_404_error_does_not_mark_stopped(self, app: Flask, db_session: Session) -> None:
        """A 5xx (non-404) error must not permanently mark the job stopped."""
        experiment = _make_experiment(db_session)
        job = _make_tuner_job(experiment)
        db_session.add(job)
        db_session.commit()

        server_error_response = Mock(status_code=HTTPStatus.INTERNAL_SERVER_ERROR)
        with patch(
            "models.tuner_job.tuner.amber_poll_status",
            side_effect=HTTPError("boom", response=server_error_response),
        ):
            status = job._status()

        assert status == {}
        assert job.is_stopped is False

    def test_successful_poll_does_not_mark_stopped(self, app: Flask, db_session: Session) -> None:
        """A successful status poll must leave the job running."""
        experiment = _make_experiment(db_session)
        job = _make_tuner_job(experiment)
        db_session.add(job)
        db_session.commit()

        ok_status = {"status": JobStatus.RUNNING, "trials": []}
        with patch("models.tuner_job.tuner.amber_poll_status", return_value=ok_status):
            status = job._status()

        assert status == ok_status
        assert job.is_stopped is False


class TestTunerJobFinished:
    """A FINISHED job must be persisted dashboard-side and stop polling the tuner."""

    def setup_method(self) -> None:
        """Clear tuner caches before each test."""
        tuner_status_cache.clear()
        tuner_last_known_status.clear()

    def teardown_method(self) -> None:
        """Clear tuner caches after each test."""
        tuner_status_cache.clear()
        tuner_last_known_status.clear()

    def test_finished_poll_stops_job_and_preserves_trials(self, app: Flask, db_session: Session) -> None:
        """A FINISHED status flips the job stopped and keeps performance-bearing trials."""
        experiment = _make_experiment(db_session)
        job = _make_tuner_job(experiment)
        db_session.add(job)
        db_session.commit()

        finished_status = {
            "status": JobStatus.FINISHED,
            "trials": [
                {"id": "t1", "performance": EXPECTED_PERFORMANCE},
                {"id": "t2", "performance": None},
            ],
        }
        with (
            patch(
                "models.tuner_job.tuner.amber_poll_status", side_effect=[finished_status, AssertionError("re-polled")]
            ),
            patch("models.tuner_job.tuner.amber_delete_job") as mock_delete,
        ):
            status = job._status()
            job._status()

        assert status == finished_status
        assert job.is_stopped is True
        assert mock_delete.call_count == 1
        preserved = job.trials
        assert len(preserved) == 1
        assert preserved[0]["performance"] == pytest.approx(EXPECTED_PERFORMANCE)


class TestTunerJobErrorStatus:
    """An ERROR status from the tuner must always populate error_message."""

    def setup_method(self) -> None:
        """Clear tuner caches before each test."""
        tuner_status_cache.clear()
        tuner_last_known_status.clear()

    def teardown_method(self) -> None:
        """Clear tuner caches after each test."""
        tuner_status_cache.clear()
        tuner_last_known_status.clear()

    def test_error_status_with_message_sets_error_message(self, app: Flask, db_session: Session) -> None:
        """A tuner ERROR response with an error field must persist that message."""
        experiment = _make_experiment(db_session)
        job = _make_tuner_job(experiment)
        db_session.add(job)
        db_session.commit()

        error_status = {"status": JobStatus.ERROR, "error": "Tuner exploded", "trials": []}
        with patch("models.tuner_job.tuner.amber_poll_status", return_value=error_status):
            status = job._status()

        assert status == error_status
        assert job.error_message == "Tuner exploded"

    def test_error_status_without_message_sets_default_error_message(self, app: Flask, db_session: Session) -> None:
        """A tuner ERROR response without an error field must get a default message."""
        experiment = _make_experiment(db_session)
        job = _make_tuner_job(experiment)
        db_session.add(job)
        db_session.commit()

        error_status = {"status": JobStatus.ERROR, "trials": []}
        with patch("models.tuner_job.tuner.amber_poll_status", return_value=error_status):
            status = job._status()

        assert status == error_status
        assert job.error_message == "Tuning job failed on the tuner."


class TestTunerJobStartFailure:
    """A tuner submit failure must surface as a friendly upstream-unavailable error."""

    @pytest.mark.parametrize(
        "exc",
        [
            HTTPError("tuner returned 500"),
            RequestsConnectionError("tuner unreachable"),
        ],
        ids=["http-error", "connection-error"],
    )
    def test_submit_failure_raises_upstream_unavailable(self, app: Flask, db_session: Session, exc) -> None:
        """Any requests exception from the tuner client must become an upstream-unavailable ApiError."""
        from errors import ApiError

        experiment = _make_experiment(db_session)
        simulation = Mock()
        simulation.extra_args = ""

        with (
            patch("models.tuner_job.Simulation.get", return_value=simulation),
            patch("models.tuner_job.tuner.amber_submit", side_effect=exc),
            pytest.raises(ApiError) as exc_info,
        ):
            TunerJob.start(experiment, "production/test.simulation.json", nsteps=1000)

        assert exc_info.value.problem_type == "urn:mddash:upstream-unavailable"
        assert exc_info.value.code == HTTPStatus.INTERNAL_SERVER_ERROR
        assert exc_info.value.problem_solution is not None


class TestTunerStatusCoercion:
    """The status dict carries raw JSON strings; tuner_status must still return JobStatus members."""

    def setup_method(self) -> None:
        """Clear tuner caches before each test."""
        tuner_status_cache.clear()
        tuner_last_known_status.clear()

    def teardown_method(self) -> None:
        """Clear tuner caches after each test."""
        tuner_status_cache.clear()
        tuner_last_known_status.clear()

    def test_raw_string_status_is_coerced(self, app: Flask, db_session: Session) -> None:
        """A raw "RUNNING" from the tuner becomes the RUNNING member, and the job is live."""
        experiment = _make_experiment(db_session)
        job = _make_tuner_job(experiment)
        db_session.add(job)
        db_session.commit()

        with patch("models.tuner_job.tuner.amber_poll_status", return_value={"status": "RUNNING", "trials": []}):
            assert job.tuner_status is JobStatus.RUNNING
            assert job.is_live is True

    def test_unknown_status_string_degrades_to_unknown(self, app: Flask, db_session: Session) -> None:
        """A status outside the enum vocabulary reads as UNKNOWN rather than raising."""
        experiment = _make_experiment(db_session)
        job = _make_tuner_job(experiment)
        db_session.add(job)
        db_session.commit()

        with patch("models.tuner_job.tuner.amber_poll_status", return_value={"status": "FUTURE_STATE", "trials": []}):
            assert job.tuner_status is JobStatus.UNKNOWN
            assert job.is_live is True

    def test_stopped_job_is_not_live(self, app: Flask, db_session: Session) -> None:
        """A stopped job reports UNKNOWN (from the empty status dict) but is terminal."""
        experiment = _make_experiment(db_session)
        job = _make_tuner_job(experiment)
        job.is_stopped = True
        db_session.add(job)
        db_session.commit()

        assert job.tuner_status is JobStatus.UNKNOWN
        assert job.is_live is False
