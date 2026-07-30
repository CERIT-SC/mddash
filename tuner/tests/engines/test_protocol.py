from api.engines.protocol import Engine, TrialConfig, TrialResult


def test_trial_config_stores_params() -> None:
    cfg = TrialConfig(num_cpus=4, num_gpus=1, params={"binary": "pmemd.cuda", "np": 1})
    assert cfg.num_cpus == 4
    assert cfg.num_gpus == 1
    assert cfg.params["binary"] == "pmemd.cuda"


def test_trial_result_fields() -> None:
    r = TrialResult(performance=12.5, steps_per_sec=1500.0, early_stopped=False)
    assert r.performance == 12.5
    assert not r.early_stopped


def test_engine_protocol_is_structural() -> None:
    """Any class with generate_configs + run_trial + simulation_length_ns satisfies Engine without inheriting."""

    class FakeEngine:
        def generate_configs(self):
            return []

        def run_trial(self, config, trial_id, job_id, nsteps, extra_args, best_steps_per_sec):
            return TrialResult(performance=0.0, steps_per_sec=0.0, early_stopped=False)

        def simulation_length_ns(self, job_id):
            return None

    engine: Engine = FakeEngine()  # type: ignore[assignment]
    assert engine.generate_configs() == []
    assert engine.simulation_length_ns("job-1") is None
