import signal
from unittest.mock import MagicMock, patch

import pytest
from api.config import EARLY_STOP_COST_RATIO, EARLY_STOP_THRESHOLD, EARLY_STOP_WARMUP_STEPS
from api.engines.amber import runner
from api.engines.amber.config import AmberBinary, AmberTrialConfig, EwaldPreset
from api.engines.amber.runner import _parse_amber_performance, _parse_amber_progress, _should_early_stop, run_pmemd


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


SAMPLE_MDOUT = """\
 NSTEP =     5000   TIME(PS) =      10.000  TEMP(K) =   300.12
|      Average timings for last    5000 steps:
|      Elapsed(s) =      64.4 Per Step(ms) =      12.9
|      ns/day =     13.4 seconds/ns =    6436.2
|      Average timings for all steps:
|      Elapsed(s) =      64.4 Per Step(ms) =      12.9
|      ns/day =     13.5 seconds/ns =    6436.2
"""

SAMPLE_MDINFO = """\
|  Master Total CPU time:         64.41 seconds
|
|        Nstep =     5000    Time =      10.000
|      ns/day =     13.4 seconds/ns =    6436.2
"""


def test_parse_performance_returns_last_match() -> None:
    # Last ns/day in mdout is the "all steps" summary — should be 13.5
    result = _parse_amber_performance(SAMPLE_MDOUT)
    assert result == 13.5


def test_parse_performance_returns_zero_on_empty() -> None:
    assert _parse_amber_performance("") == 0.0


def test_parse_performance_returns_zero_on_no_match() -> None:
    assert _parse_amber_performance("no performance data here") == 0.0


def test_monitor_interruption_terminates_native_process_group(tmp_path, monkeypatch) -> None:
    process = MagicMock()
    process.poll.return_value = None
    popen = MagicMock()
    popen.return_value.__enter__.return_value = process
    monkeypatch.setattr(runner.subprocess, "Popen", popen)
    monkeypatch.setattr(runner, "_monitor_process", MagicMock(side_effect=KeyboardInterrupt))
    terminate = MagicMock()
    monkeypatch.setattr(runner, "_terminate_process_group", terminate)

    with pytest.raises(KeyboardInterrupt):
        runner._run_command_with_monitoring(
            ["pmemd"], tmp_path / "mdout", tmp_path / "mdinfo", tmp_path, "test trial", 0.0, {}, 0.0, 0.0
        )

    terminate.assert_called_once_with(process, signal.SIGTERM)
    process.wait.assert_called_once_with(timeout=30)


def test_parse_progress_returns_step() -> None:
    result = _parse_amber_progress(SAMPLE_MDINFO)
    assert result == 5000


def test_parse_progress_returns_none_on_empty() -> None:
    assert _parse_amber_progress("") is None


def test_parse_progress_returns_none_on_no_match() -> None:
    assert _parse_amber_progress("no steps here") is None


def test_mpi_run_sets_omp_num_threads(tmp_path, monkeypatch) -> None:
    """pmemd.MPI subprocess receives OMP_NUM_THREADS equal to config.ntomp."""
    monkeypatch.setattr("api.engines.amber.runner.JOBS_DIR", tmp_path / "jobs")
    monkeypatch.setattr("api.engines.amber.runner.INPUTS_DIR", tmp_path)

    (tmp_path / "job1_md.prmtop").write_text("")
    (tmp_path / "job1_md.inpcrd").write_text("")
    (tmp_path / "job1_md.mdin").write_text(" &cntrl\n  nstlim = 100,\n /\n")

    config = AmberTrialConfig(binary=AmberBinary.PMEMD_MPI, np=1, ewald=EwaldPreset.DEFAULT, ntomp=2)

    captured_env: dict = {}

    mock_proc = MagicMock()
    mock_proc.poll.return_value = 0  # exits immediately — no monitoring loop
    mock_proc.returncode = 0
    mock_proc.pid = 99999
    mock_proc.__enter__ = MagicMock(return_value=mock_proc)
    mock_proc.__exit__ = MagicMock(return_value=False)

    def fake_popen(_cmd: list[str], **kwargs: object) -> object:
        captured_env.update(kwargs.get("env", {}))
        return mock_proc

    with patch("subprocess.Popen", fake_popen):
        run_pmemd(config, "t1", "job1", nsteps=100)

    assert captured_env.get("OMP_NUM_THREADS") == "2"
