from enum import Enum


class PopulationStatus(str, Enum):
    """Lifecycle of a Datahugger-NG population operation (member name == wire value)."""

    queued = "queued"
    running = "running"
    succeeded = "succeeded"
    failed = "failed"

    @classmethod
    def active(cls) -> frozenset["PopulationStatus"]:
        """States the app-lifespan monitor still reconciles."""
        return frozenset({cls.queued, cls.running})

    def __str__(self) -> str:
        return self.value
