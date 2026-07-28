"""Cost estimation for tuning trials based on hourly resource rates."""

import os
from dataclasses import dataclass

# Hourly resource rates in currency units, overridable per deployment.
COST_CPU_CORE_HOUR = float(os.getenv("COST_CPU_CORE_HOUR", "0.04"))
COST_GPU_HOUR = float(os.getenv("COST_GPU_HOUR", "3.00"))
COST_GB_RAM_HOUR = float(os.getenv("COST_GB_RAM_HOUR", "0.005"))

# RAM allocated per MPI rank, mirroring mdrun-api k8s resource requests.
RAM_GB_PER_RANK = 4.0


@dataclass(frozen=True)
class ResourceFootprint:
    """Compute resources a trial config would be allocated in production (mirrors mdrun-api)."""

    cores: int
    gpus: int
    ram_gb: float

    def hourly_cost(self) -> float:
        """Hourly cost of this footprint at the configured rates."""
        return self.cores * COST_CPU_CORE_HOUR + self.gpus * COST_GPU_HOUR + self.ram_gb * COST_GB_RAM_HOUR

    def estimate(self, sim_length_ns: float | None, performance: float | None) -> tuple[float | None, float | None]:
        """
        Estimate wall-clock hours and cost to run the full simulation with this footprint.

        Returns (estimated_time, estimated_cost); both are None when the simulation
        length or measured performance is unavailable.
        """
        if sim_length_ns is None or sim_length_ns <= 0 or performance is None or performance <= 0:
            return None, None
        estimated_time = sim_length_ns / performance * 24.0  # performance is in ns/day
        return estimated_time, estimated_time * self.hourly_cost()
