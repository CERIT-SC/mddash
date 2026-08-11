import signal
from unittest.mock import MagicMock

import pytest
from api.config import EARLY_STOP_COST_RATIO, EARLY_STOP_THRESHOLD, EARLY_STOP_WARMUP_STEPS
from api.engines.gmx import runner
from api.engines.gmx.runner import _should_early_stop


class TestShouldEarlyStop:
    best_steps = 100.0
    best_cost_per_step = 0.01

    def stop(self, sps_ratio: float, cost_ratio: float, step: int = EARLY_STOP_WARMUP_STEPS + 1) -> bool:
        return _should_early_stop(
            step,
            120.0,
            self.best_steps * sps_ratio,
            self.best_steps,
            self.best_cost_per_step * cost_ratio,
            self.best_cost_per_step,
        )

    def test_slow_but_cheap_explores(self) -> None:
        assert not self.stop(0.5 * EARLY_STOP_THRESHOLD, 0.5 * EARLY_STOP_COST_RATIO)

    def test_slow_and_expensive_dies(self) -> None:
        assert self.stop(0.5 * EARLY_STOP_THRESHOLD, 2 * EARLY_STOP_COST_RATIO)

    def test_fast_but_expensive_explores(self) -> None:
        assert not self.stop(2.0, 2 * EARLY_STOP_COST_RATIO)

    def test_close_but_expensive_dies(self) -> None:
        assert self.stop(EARLY_STOP_THRESHOLD - 0.05, 2 * EARLY_STOP_COST_RATIO)

    def test_no_prune_before_warmup(self) -> None:
        step = EARLY_STOP_WARMUP_STEPS - 1
        assert not _should_early_stop(
            step, 10.0, self.best_steps * 0.01, self.best_steps, self.best_cost_per_step * 10, self.best_cost_per_step
        )

    def test_no_prune_without_best_reference(self) -> None:
        assert not _should_early_stop(EARLY_STOP_WARMUP_STEPS + 1, 120.0, 50.0, 0.0, 0.05, 0.0)


def test_monitor_interruption_terminates_native_process_group(tmp_path, monkeypatch) -> None:
    process = MagicMock()
    process.poll.return_value = None
    monkeypatch.setattr(runner.subprocess, "Popen", MagicMock(return_value=process))
    monkeypatch.setattr(runner, "_monitor_process", MagicMock(side_effect=KeyboardInterrupt))
    terminate = MagicMock()
    monkeypatch.setattr(runner, "_terminate_process_group", terminate)

    with pytest.raises(KeyboardInterrupt):
        runner._run_command_with_monitoring(
            ["gmx"], tmp_path / "stdout.log", tmp_path / "stderr.log", {}, tmp_path, "test trial", 0.0, 0.0, 0.0
        )

    terminate.assert_called_once_with(process, signal.SIGTERM)
    process.wait.assert_called_once_with(timeout=30)
