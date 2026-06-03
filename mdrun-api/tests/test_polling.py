"""Tests for mdrun-api polling helpers."""

from unittest.mock import PropertyMock

from enums import JobStatus
from models import MdrunJob
from polling import poll_once
from sqlalchemy.orm import Session

EXPECTED_POLLED_JOBS = 2


def test_poll_once_updates_active_jobs_only(app, db_session: Session, mocker) -> None:  # noqa: ANN001
    """One-shot polling should touch only active jobs."""
    active_job = MdrunJob(id="active", job_name="mdrun-active", experiment_id="exp1", last_status=JobStatus.RUNNING)
    done_job = MdrunJob(id="done", job_name="mdrun-done", experiment_id="exp2", last_status=JobStatus.TERMINATED)
    db_session.add_all([active_job, done_job])
    db_session.commit()
    status = mocker.patch.object(MdrunJob, "status", new_callable=PropertyMock, return_value=JobStatus.RUNNING)

    poll_once(app)

    status.assert_called_once_with()


def test_poll_once_continues_when_job_status_refresh_fails(app, db_session: Session, mocker) -> None:  # noqa: ANN001
    """A single failed job refresh should not abort the poll run."""
    first_job = MdrunJob(id="first", job_name="mdrun-first", experiment_id="exp1", last_status=JobStatus.RUNNING)
    second_job = MdrunJob(id="second", job_name="mdrun-second", experiment_id="exp2", last_status=JobStatus.PENDING)
    db_session.add_all([first_job, second_job])
    db_session.commit()
    status = mocker.patch.object(
        MdrunJob,
        "status",
        new_callable=PropertyMock,
        side_effect=[RuntimeError("boom"), JobStatus.RUNNING],
    )

    poll_once(app)

    assert status.call_count == EXPECTED_POLLED_JOBS
