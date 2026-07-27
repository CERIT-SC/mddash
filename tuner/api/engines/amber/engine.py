"""AmberEngine — adapts AmberTrialConfig and run_pmemd to the Engine protocol."""

from dataclasses import dataclass

from api.engines.amber.config import AmberTrialConfig
from api.engines.amber.runner import run_pmemd
from api.engines.protocol import TrialConfig, TrialResult


@dataclass
class AmberEngine:
    """Engine implementation for AMBER pmemd."""

    def generate_configs(self) -> list[TrialConfig]:
        """Return all AMBER trial configs wrapped in the engine-agnostic TrialConfig type."""
        return [
            TrialConfig(num_cpus=c.num_cpus, num_gpus=c.num_gpus, params=c.to_dict())
            for c in AmberTrialConfig.generate_all_configs()
        ]

    def run_trial(
        self,
        config: TrialConfig,
        trial_id: str,
        job_id: str,
        nsteps: int,
        extra_args: str,
        best_steps_per_sec: float,
    ) -> TrialResult:
        """Execute one pmemd trial and return the result."""
        perf, sps, early = run_pmemd(
            AmberTrialConfig.from_dict(config.params),
            trial_id,
            job_id,
            extra_args,
            nsteps,
            best_steps_per_sec,
        )
        return TrialResult(performance=perf, steps_per_sec=sps, early_stopped=early)
