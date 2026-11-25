from enum import Enum


class PopulationStatus(str, Enum):
    """Lifecycle of a Datahugger-NG population operation (member name == wire value)."""

    queued = "queued"
    running = "running"
    cancelling = "cancelling"
    succeeded = "succeeded"
    failed = "failed"
    cancelled = "cancelled"

    @classmethod
    def active(cls) -> frozenset["PopulationStatus"]:
        """States the app-lifespan monitor still reconciles."""
        return frozenset({cls.queued, cls.running})

    @classmethod
    def cancellable(cls) -> frozenset["PopulationStatus"]:
        """States that can still enter cancellation or finish an interrupted one."""
        return frozenset({cls.queued, cls.running, cls.cancelling})

    def __str__(self) -> str:
        return self.value
