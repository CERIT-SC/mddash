from enum import Enum


class NotebookTier(str, Enum):
    """Resource multiplier tiers for notebook pods."""

    SMALL = "1x"
    MEDIUM = "2x"
    LARGE = "4x"

    def __str__(self) -> str:
        return self.value

    @property
    def multiplier(self) -> int:
        """Return the integer multiplier for this tier (1, 2, or 4)."""
        return int(self.value.rstrip("x"))
