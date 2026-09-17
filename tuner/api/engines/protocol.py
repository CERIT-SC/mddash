"""Engine protocol and shared trial types."""

from dataclasses import dataclass
from typing import Any, Protocol


@dataclass
class TrialConfig:
    """Engine-agnostic trial descriptor passed through the orchestration layer."""

    num_cpus: int
    num_gpus: int
    params: dict[str, Any]  # engine-specific; stored as-is in Trial.config_json
    priority: int = 0  # higher = run sooner; engines use this to prefer better configs


@dataclass
class TrialResult:
    """Result returned by every engine after a trial."""

    # ns/day; 0.0 on failure, None when a pruned trial's timestep is unknown —
    # NULL must survive to the UI so the trial keeps no-result semantics.
    performance: float | None
    steps_per_sec: float  # used for early stopping comparison
    early_stopped: bool
    cost_per_step: float = 0.0  # footprint hourly rate / steps_per_sec; 0.0 if steps unknown


def steps_to_ns_per_day(steps_per_sec: float, dt_ps: float | None) -> float | None:
    """ns/day for a measured steps/sec at timestep dt (ps); None when either is unknown."""
    if dt_ps is None or dt_ps <= 0 or steps_per_sec <= 0:
        return None
    return steps_per_sec * dt_ps * 86400.0 / 1000.0


class Engine(Protocol):
    """Structural protocol that every MD engine must satisfy."""

    def generate_configs(self) -> list[TrialConfig]:
        """Return all trial configurations to benchmark for this engine."""
        ...

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
        """Execute a single trial and return its performance result."""
        ...

    def simulation_length_ns(self, job_id: str, nsteps_override: int | None = None) -> float | None:
        """
        Production simulation length (ns) from the original input files; None if unknown.

        Engines with a step-count CLI override (GMX mdrun -nsteps) apply it over the
        input file's step count; engines without one (AMBER pmemd) ignore the value.
        """
        ...
