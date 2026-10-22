"""Notebook resource tiers: the base resources (1x) scaled by the tier multiplier."""

from clients.k8s import parse_memory
from core.config import NOTEBOOK_RESOURCES
from core.enums import NotebookTier


def _multiply_resource(value: str, factor: int) -> str:
    if not value:
        return value
    value = value.strip()
    if value.endswith("m"):
        return f"{int(value[:-1]) * factor}m"
    if value.endswith("Gi") or value.endswith("Mi"):
        # Use parse_memory to avoid int() truncating fractional Gi/Mi values
        bytes_val = parse_memory(value) * factor
        if bytes_val % (1024**3) == 0:
            return f"{bytes_val // (1024**3)}Gi"
        return f"{bytes_val // (1024**2)}Mi"
    # Plain number (CPU cores)
    return str(float(value) * factor)


def get_tier_resources(tier: NotebookTier) -> dict:
    """
    Return notebook_resources scaled by the tier multiplier.

    The base values come from the NOTEBOOK_RESOURCES env vars (1x tier).
    Higher tiers multiply all CPU and memory values by the tier factor.

    Returns:
        A notebook_resources dict with CPU/memory scaled by the tier factor.
    """
    factor = tier.multiplier
    if factor == 1:
        return NOTEBOOK_RESOURCES

    def scale(res: dict[str, dict[str, str]]) -> dict[str, dict[str, str]]:
        return {
            category: {key: _multiply_resource(val, factor) for key, val in values.items()}
            for category, values in res.items()
        }

    return scale(NOTEBOOK_RESOURCES)
