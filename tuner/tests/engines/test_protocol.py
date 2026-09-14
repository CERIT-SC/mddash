import pytest
from api.engines.protocol import Engine, TrialConfig, TrialResult, steps_to_ns_per_day


def test_trial_config_stores_params() -> None:
    cfg = TrialConfig(num_cpus=4, num_gpus=1, params={"binary": "pmemd.cuda", "np": 1})
    assert cfg.num_cpus == 4
    assert cfg.num_gpus == 1
    assert cfg.params["binary"] == "pmemd.cuda"


def test_trial_result_fields() -> None:
    r = TrialResult(performance=12.5, steps_per_sec=1500.0, early_stopped=False)
    assert r.performance == 12.5
    assert not r.early_stopped


class TestStepsToNsPerDay:
    def test_converts(self) -> None:
        # 100 steps/s * 0.002 ps = 0.2 ps/s -> 17.28 ns/day
        assert steps_to_ns_per_day(100.0, 0.002) == pytest.approx(17.28)

    @pytest.mark.parametrize(
        ("steps_per_sec", "dt_ps"),
        [(100.0, None), (100.0, 0.0), (100.0, -0.002), (0.0, 0.002), (-1.0, 0.002)],
    )
    def test_unknown_or_nonpositive_yields_zero(self, steps_per_sec, dt_ps) -> None:
        assert steps_to_ns_per_day(steps_per_sec, dt_ps) == 0.0


def test_engine_protocol_is_structural() -> None:
    """Any class with generate_configs + run_trial + simulation_length_ns satisfies Engine without inheriting."""

    class FakeEngine:
        def generate_configs(self):
            return []

        def run_trial(self, config, trial_id, job_id, nsteps, extra_args, best_steps_per_sec, best_cost_per_step):
            return TrialResult(performance=0.0, steps_per_sec=0.0, early_stopped=False)

        def simulation_length_ns(self, job_id):
            return None

    engine: Engine = FakeEngine()  # type: ignore[assignment]
    assert engine.generate_configs() == []
    assert engine.simulation_length_ns("job-1") is None
