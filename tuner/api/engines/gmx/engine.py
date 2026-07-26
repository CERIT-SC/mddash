"""GmxEngine — adapts GmxTrialConfig and run_mdrun to the Engine protocol."""

from dataclasses import dataclass

from api.engines.gmx.config import GmxTrialConfig, NBMode, PMEMode
from api.engines.gmx.runner import run_mdrun
from api.engines.protocol import TrialConfig, TrialResult


@dataclass
class GmxEngine:
    """Engine implementation for GROMACS mdrun."""

    def generate_configs(self) -> list[TrialConfig]:
        """Return all GMX trial configs wrapped in the engine-agnostic TrialConfig type."""
        return [
            TrialConfig(
                num_cpus=c.num_cpus,
                num_gpus=c.num_gpus,
                params=c.to_dict(),
                priority=int(c.nb == NBMode.GPU) + int(c.pme == PMEMode.GPU),
            )
            for c in GmxTrialConfig.generate_all_configs()
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
        """Execute one mdrun trial and return the result."""
        perf, sps, early = run_mdrun(
            GmxTrialConfig.from_dict(config.params),
            trial_id,
            job_id,
            extra_args,
            nsteps,
            best_steps_per_sec,
        )
        return TrialResult(performance=perf, steps_per_sec=sps, early_stopped=early)
