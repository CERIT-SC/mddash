"""Shared early-stop predicate for tuning trials, used by all engine runners."""

from api.config import (
    EARLY_STOP_COST_RATIO,
    EARLY_STOP_ENABLED,
    EARLY_STOP_THRESHOLD,
    EARLY_STOP_WARMUP_SECONDS,
    EARLY_STOP_WARMUP_STEPS,
)


def _should_early_stop(
    current_step: int,
    elapsed_time: float,
    steps_per_sec: float,
    best_steps_per_sec: float,
    cost_per_step: float,
    best_cost_per_step: float,
) -> bool:
    """Prune only trials both slower and more expensive per step than the champions."""
    if best_steps_per_sec <= 0 or best_cost_per_step <= 0:
        return False
    warmup_reached = (current_step >= EARLY_STOP_WARMUP_STEPS) or (elapsed_time >= EARLY_STOP_WARMUP_SECONDS)
    too_slow = steps_per_sec < best_steps_per_sec * EARLY_STOP_THRESHOLD
    too_expensive = cost_per_step > best_cost_per_step * EARLY_STOP_COST_RATIO
    return EARLY_STOP_ENABLED and warmup_reached and too_slow and too_expensive
