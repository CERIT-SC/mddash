"""Tests for mdrun-api polling helpers."""

from unittest.mock import PropertyMock

import k8s_client
import pytest
from enums import JobStatus
from models import MdrunJob, MdrunUsage
from polling import poll_once, run
from sqlalchemy.orm import Session
from urllib3.exceptions import ProtocolError

EXPECTED_POLLED_JOBS = 2
LOOP_INTERVAL = 5
EXPECTED_LOOP_POLLS = 2


def test_poll_once_updates_active_jobs_only(app, db_session: Session, mocker) -> None:
    """One-shot polling should touch only active jobs."""
    active_job = MdrunJob(id="active", job_name="mdrun-active", experiment_id="exp1", last_status=JobStatus.RUNNING)
    done_job = MdrunJob(id="done", job_name="mdrun-done", experiment_id="exp2", last_status=JobStatus.FINISHED)
    stopped_job = MdrunJob(id="stopped", job_name="mdrun-stopped", experiment_id="exp3", last_status=JobStatus.STOPPED)
    db_session.add_all([active_job, done_job, stopped_job])
    db_session.commit()
    status = mocker.patch.object(MdrunJob, "status", new_callable=PropertyMock, return_value=JobStatus.RUNNING)

    poll_once(app)

    status.assert_called_once_with()


def test_poll_once_continues_when_job_status_refresh_fails(app, db_session: Session, mocker) -> None:
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


def test_poll_once_drops_a_failed_jobs_pending_writes(app, db_session: Session, mocker) -> None:
    """A failed job's uncommitted ledger writes must not ride on the next job's commit."""
    resources = k8s_client.JobResources(cpu=1, memory_gib=1, gpus=0)
    for job_id in ("a", "b"):
        MdrunJob.create(
            job_id, f"mdrun-{job_id}", "exp1", engine="gmx", resources=resources, owner=None, owner_namespace=None
        )
    finished = {"mdrun-a": JobStatus.FINISHED, "mdrun-b": JobStatus.RUNNING}
    mocker.patch("k8s_client.get_job_status", side_effect=lambda ns, name: finished[name])
    mocker.patch("k8s_client.get_pod_times", return_value=(None, None))
    # The cleanup delete gets no answer after the window close was written.
    mocker.patch("k8s_client.delete_job", side_effect=ProtocolError("reset"))

    poll_once(app)

    db_session.expire_all()
    usage = db_session.get(MdrunUsage, "a")
    assert usage is not None
    assert usage.finished_at is None
    polled = db_session.get(MdrunJob, "b")
    assert polled is not None
    assert polled.last_status == JobStatus.RUNNING


def test_run_loops_and_sleeps_between_polls(app, mocker) -> None:
    """The poller should poll, sleep, then poll again."""
    poll = mocker.patch("polling.poll_once", side_effect=[None, StopIteration])
    sleep = mocker.patch("polling.time.sleep")

    # The second poll_once raises, breaking the loop after one full iteration.
    with pytest.raises(StopIteration):
        run(app, LOOP_INTERVAL)

    assert poll.call_count == EXPECTED_LOOP_POLLS
    sleep.assert_called_once_with(LOOP_INTERVAL)
