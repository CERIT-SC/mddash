from unittest.mock import Mock

import pytest
from api.rayworker import tuner
from api.schemas.common import JobStatus


@pytest.fixture
def job_context(monkeypatch) -> tuner.JobContext:
    ctx = tuner.JobContext()
    monkeypatch.setattr(tuner, "_job_context", ctx)
    return ctx


def test_ensure_ray_initialized_uses_single_client_connection(monkeypatch) -> None:
    ray_mock = Mock()
    ray_mock.is_initialized.return_value = False
    monkeypatch.setattr(tuner, "ray", ray_mock)

    tuner._ensure_ray_initialized()

    ray_mock.init.assert_called_once()
    _, kwargs = ray_mock.init.call_args
    assert "allow_multiple" not in kwargs


class TestTaskStates:
    """_task_states maps active futures to their Ray task states."""

    def test_maps_reported_states(self, job_context, monkeypatch) -> None:
        future_a, future_b = Mock(), Mock()
        future_a.task_id.return_value = "task-a"
        future_b.task_id.return_value = "task-b"
        job_context.add_job("j1", Mock())
        job_context.add_futures("j1", {future_a: 1, future_b: 2})
        monkeypatch.setattr(tuner, "get_task", lambda task_id, address=None: Mock(state="RUNNING"))
        assert tuner._task_states("j1") == {1: "RUNNING", 2: "RUNNING"}

    def test_skips_unknown_and_failed_queries(self, job_context, monkeypatch) -> None:
        future_a, future_b, future_c = Mock(), Mock(), Mock()
        for i, future in enumerate((future_a, future_b, future_c)):
            future.task_id.return_value = f"task-{i}"
        job_context.add_job("j1", Mock())
        job_context.add_futures("j1", {future_a: 1, future_b: 2, future_c: 3})

        def fake_get_task(task_id, address=None):
            if task_id == "task-0":
                return Mock(state="RUNNING")
            if task_id == "task-1":
                return None  # task not yet visible in GCS
            raise RuntimeError("dashboard unavailable")

        monkeypatch.setattr(tuner, "get_task", fake_get_task)
        assert tuner._task_states("j1") == {1: "RUNNING"}


class TestTrialStatusOverrides:
    """trial_status_overrides exposes only trials Ray reports as executing."""

    def test_only_running_states_are_overridden(self, monkeypatch) -> None:
        monkeypatch.setattr(
            tuner,
            "_task_states",
            lambda job_id: {1: "RUNNING", 2: "PENDING_NODE_ASSIGNMENT", 3: "FINISHED"},
        )
        assert tuner.trial_status_overrides("j1") == {1: JobStatus.RUNNING}


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
    def test_stall_fails_remaining_trials_and_raises(self, job_context, monkeypatch) -> None:
        """No completion in the timeout window and nothing executing => unschedulable."""
        future = Mock()
        ray_mock = Mock()
        ray_mock.wait.return_value = ([], [future])
        monkeypatch.setattr(tuner, "ray", ray_mock)
        monkeypatch.setattr(tuner, "_task_states", lambda job_id: {})
        monkeypatch.setattr(tuner, "update_trial_result", Mock())

        with pytest.raises(RuntimeError, match="cluster busy or unavailable"):
            tuner._process_trial_results("j1", {future: 7}, 0.0)

        _, kwargs = ray_mock.wait.call_args
        assert kwargs["timeout"] == tuner.TRIAL_START_TIMEOUT_SECONDS
        ray_mock.cancel.assert_called_once_with(future, force=False)
        tuner.update_trial_result.assert_called_once_with(7, JobStatus.ERROR, None)

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
        monkeypatch.setattr(tuner, "_task_states", lambda job_id: {7: "RUNNING"})
        monkeypatch.setattr(tuner, "update_trial_result", Mock())

        best = tuner._process_trial_results("j1", {future: 7}, 0.0)

        assert best == 10.0
        tuner.update_trial_result.assert_called_once_with(7, JobStatus.FINISHED, 42.0)
