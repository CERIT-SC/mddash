"""GmxEngine — adapts GmxTrialConfig and run_mdrun to the Engine protocol."""

from dataclasses import dataclass

from api.config import INPUTS_DIR
from api.engines.gmx.config import GmxTrialConfig, NBMode, PMEMode
from api.engines.gmx.runner import run_mdrun
from api.engines.gmx.tprinfo import simulation_length_ns as tpr_simulation_length_ns
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
        best_cost_per_step: float,
    ) -> TrialResult:
        """Execute one mdrun trial and return the result."""
        gmx_config = GmxTrialConfig.from_dict(config.params)
        perf, sps, early = run_mdrun(
            gmx_config, trial_id, job_id, extra_args, nsteps, best_steps_per_sec, best_cost_per_step
        )
        cost = gmx_config.footprint.hourly_cost() / sps if sps > 0 else 0.0
        return TrialResult(performance=perf, steps_per_sec=sps, early_stopped=early, cost_per_step=cost)

    def simulation_length_ns(self, job_id: str, nsteps_override: int | None = None) -> float | None:
        """Extract nsteps * delta_t from the job's .tpr via `gmx dump` on a Ray worker; -nsteps override wins."""
        return tpr_simulation_length_ns(str(INPUTS_DIR / f"{job_id}_md.tpr"), nsteps_override)
