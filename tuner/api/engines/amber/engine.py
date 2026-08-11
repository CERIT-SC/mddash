"""AmberEngine — adapts AmberTrialConfig and run_pmemd to the Engine protocol."""

import logging
from dataclasses import dataclass

from api.config import INPUTS_DIR
from api.engines.amber.config import AmberTrialConfig
from api.engines.amber.mdin import simulation_length_ns as mdin_simulation_length_ns
from api.engines.amber.runner import run_pmemd
from api.engines.protocol import TrialConfig, TrialResult

logger = logging.getLogger(__name__)


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
        best_cost_per_step: float,
    ) -> TrialResult:
        """Execute one pmemd trial and return the result."""
        amber_config = AmberTrialConfig.from_dict(config.params)
        perf, sps, early = run_pmemd(
            amber_config, trial_id, job_id, extra_args, nsteps, best_steps_per_sec, best_cost_per_step
        )
        cost = amber_config.footprint.hourly_cost() / sps if sps > 0 else 0.0
        return TrialResult(performance=perf, steps_per_sec=sps, early_stopped=early, cost_per_step=cost)

    def simulation_length_ns(self, job_id: str, nsteps_override: int | None = None) -> float | None:  # ruff: ignore[unused-method-argument]
        """Parse nstlim * dt from the job's original uploaded mdin file (pmemd has no step-count CLI override)."""
        try:
            content = (INPUTS_DIR / f"{job_id}_md.mdin").read_text(encoding="utf-8", errors="replace")
        except OSError:
            logger.warning("Could not read mdin for job %s", job_id)
            return None
        return mdin_simulation_length_ns(content)
