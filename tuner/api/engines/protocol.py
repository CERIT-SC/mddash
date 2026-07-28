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

    performance: float  # ns/day; 0.0 on failure
    steps_per_sec: float  # used for early stopping comparison
    early_stopped: bool


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
    ) -> TrialResult:
        """Execute a single trial and return its performance result."""
        ...

    def simulation_length_ns(self, job_id: str) -> float | None:
        """Production simulation length (ns) from the original input files; None if unknown."""
        ...
