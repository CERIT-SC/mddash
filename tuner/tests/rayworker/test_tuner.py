from unittest.mock import Mock

import pytest
from api.db.models import init_db
from api.db.operations import create_job, create_trial_result, get_trial, get_trials_by_job_id, update_job_status
from api.rayworker import tuner
from api.schemas.common import JobStatus, MDEngine


@pytest.fixture
def db_schema() -> None:
    """Ensure the temp DB has tables (init_db runs at app startup, not import)."""
    init_db()


@pytest.fixture
def job_context(monkeypatch) -> tuner.JobContext:
    ctx = tuner.JobContext()
    monkeypatch.setattr(tuner, "_job_context", ctx)
    return ctx


def test_ensure_ray_initialized_always_inits_and_is_reinit_safe(monkeypatch) -> None:
    ray_mock = Mock()
    monkeypatch.setattr(tuner, "ray", ray_mock)

    tuner._ensure_ray_initialized()
    tuner._ensure_ray_initialized()

    assert ray_mock.init.call_count == 2
    for call in ray_mock.init.call_args_list:
        assert call.kwargs["ignore_reinit_error"] is True
        assert "allow_multiple" not in call.kwargs


class TestRunningTrialIds:
    """_running_trial_ids intersects the job's futures with one filtered State API query."""

    def test_maps_running_task_ids_to_trials(self, job_context, monkeypatch) -> None:
        future_a, future_b = Mock(), Mock()
        future_a.task_id.return_value = "task-a"
        future_b.task_id.return_value = "task-b"
        job_context.add_job("j1", Mock())
        job_context.add_futures("j1", {future_a: 1, future_b: 2})
        list_tasks_mock = Mock(return_value=[Mock(task_id="task-a")])
        monkeypatch.setattr(tuner, "list_tasks", list_tasks_mock)

        assert tuner._running_trial_ids("j1") == {1}

        _, kwargs = list_tasks_mock.call_args
        assert kwargs["filters"] == [("state", "=", "RUNNING")]

    def test_query_failure_returns_none(self, job_context, monkeypatch) -> None:
        monkeypatch.setattr(tuner, "list_tasks", Mock(side_effect=RuntimeError("dashboard unavailable")))
        assert tuner._running_trial_ids("j1") is None


class TestTrialStatusOverrides:
    """trial_status_overrides exposes only trials Ray reports as executing."""

    def test_running_trials_are_overridden(self, monkeypatch) -> None:
        monkeypatch.setattr(tuner, "_running_trial_ids", lambda job_id: {1})
        assert tuner.trial_status_overrides("j1") == {1: JobStatus.RUNNING}

    def test_state_api_outage_yields_empty_overrides(self, monkeypatch) -> None:
        """Conservative on probe failure: trials render PENDING rather than guessed."""
        monkeypatch.setattr(tuner, "_running_trial_ids", lambda job_id: None)
        assert tuner.trial_status_overrides("j1") == {}


class TestDeriveJobStatus:
    @pytest.mark.parametrize(
        ("db_status", "trial_statuses", "expected"),
        [
            (JobStatus.FINISHED, [JobStatus.RUNNING], JobStatus.FINISHED),  # terminal wins
            (JobStatus.ERROR, [JobStatus.RUNNING], JobStatus.ERROR),
            (JobStatus.RUNNING, [], JobStatus.PENDING),  # nothing executed yet
            (JobStatus.RUNNING, [JobStatus.PENDING, JobStatus.PENDING], JobStatus.PENDING),
            (JobStatus.RUNNING, [JobStatus.PENDING, JobStatus.RUNNING], JobStatus.RUNNING),
            (JobStatus.PENDING, [JobStatus.FINISHED, JobStatus.PENDING], JobStatus.RUNNING),
            (JobStatus.RUNNING, [JobStatus.ERROR], JobStatus.RUNNING),  # trial error != job terminal
        ],
    )
    def test_derivation(self, db_status, trial_statuses, expected) -> None:
        assert tuner.derive_job_status(db_status, trial_statuses) == expected


class TestSubmitTrials:
    def test_submission_keeps_trials_pending(self, job_context, monkeypatch) -> None:
        """Trials stay PENDING until Ray reports execution; no optimistic RUNNING write."""
        future = Mock()
        monkeypatch.setattr(tuner, "update_trial_result", Mock())
        runner = Mock()
        runner.options.return_value.remote.return_value = future
        monkeypatch.setattr(tuner, "_run_single_trial", runner)
        cfg = Mock(num_cpus=2, num_gpus=1, params={})
        job_context.add_job("j1", Mock())

        mapping = tuner._submit_trials("j1", "", [(7, cfg)], Mock(), 1000, 0.0)

        assert mapping == {future: 7}
        tuner.update_trial_result.assert_not_called()
        assert job_context.get_futures("j1") == {future: 7}


class TestProcessTrialResultsWatchdog:
    def test_stall_fails_and_cancels_when_nothing_is_running(self, job_context, monkeypatch) -> None:
        """Successful query + no RUNNING trials after the window => unschedulable."""
        future = Mock()
        ray_mock = Mock()
        ray_mock.wait.return_value = ([], [future])
        monkeypatch.setattr(tuner, "ray", ray_mock)
        monkeypatch.setattr(tuner, "_running_trial_ids", lambda job_id: set())

        with pytest.raises(RuntimeError, match="cluster busy or unavailable"):
            tuner._process_trial_results("j1", {future: 7}, 0.0)

        _, kwargs = ray_mock.wait.call_args
        assert kwargs["timeout"] == tuner.TRIAL_START_TIMEOUT_SECONDS
        ray_mock.cancel.assert_called_once_with(future, force=False)

    def test_executing_trial_extends_the_window(self, job_context, monkeypatch) -> None:
        """An executing trial means progress; the watchdog keeps waiting."""
        future = Mock()
        ray_mock = Mock()
        ray_mock.wait.side_effect = [([], [future]), ([future], [])]
        ray_mock.get.return_value = {
            "trial_id": "7",
            "status": JobStatus.FINISHED,
            "performance": 42.0,
            "steps_per_sec": 10.0,
            "early_stopped": False,
        }
        monkeypatch.setattr(tuner, "ray", ray_mock)
        monkeypatch.setattr(tuner, "_running_trial_ids", lambda job_id: {7})
        monkeypatch.setattr(tuner, "update_trial_result", Mock())

        best = tuner._process_trial_results("j1", {future: 7}, 0.0)

        assert best == 10.0
        tuner.update_trial_result.assert_called_once_with(7, JobStatus.FINISHED, 42.0)

    def test_state_api_outage_extends_the_window(self, job_context, monkeypatch) -> None:
        """A failed query must never false-kill a progressing job."""
        future = Mock()
        ray_mock = Mock()
        ray_mock.wait.side_effect = [([], [future]), ([future], [])]
        ray_mock.get.return_value = {
            "trial_id": "7",
            "status": JobStatus.FINISHED,
            "performance": 42.0,
            "steps_per_sec": 10.0,
            "early_stopped": False,
        }
        monkeypatch.setattr(tuner, "ray", ray_mock)
        monkeypatch.setattr(tuner, "_running_trial_ids", lambda job_id: None)
        monkeypatch.setattr(tuner, "update_trial_result", Mock())

        best = tuner._process_trial_results("j1", {future: 7}, 0.0)

        assert best == 10.0
        ray_mock.cancel.assert_not_called()


@pytest.mark.usefixtures("db_schema")
class TestErrorPendingTrials:
    def test_marks_only_pending_trials_error(self) -> None:
        job_id = "sweep-test-job"
        create_job(job_id, MDEngine.GMX)
        pending_id = create_trial_result(job_id, {}, JobStatus.PENDING, None)
        finished_id = create_trial_result(job_id, {}, JobStatus.FINISHED, 10.0)

        tuner._error_pending_trials(job_id)

        statuses = {t.id: t.status for t in get_trials_by_job_id(job_id)}
        assert statuses[pending_id] == JobStatus.ERROR
        assert statuses[finished_id] == JobStatus.FINISHED


@pytest.mark.usefixtures("db_schema")
class TestSyncJobStatusSweep:
    def test_dead_thread_job_errors_and_sweeps_pending_trials(self, job_context) -> None:
        job_id = "sync-sweep-test-job"
        create_job(job_id, MDEngine.GMX)
        trial_id = create_trial_result(job_id, {}, JobStatus.PENDING, None)
        update_job_status(job_id, JobStatus.RUNNING)  # no registered thread => dead

        assert tuner.sync_job_status(job_id) == JobStatus.ERROR
        assert get_trial(trial_id, job_id).status == JobStatus.ERROR
