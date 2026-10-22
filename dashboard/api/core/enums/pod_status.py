from enum import Enum


class PodStatus(str, Enum):
    """Status values for Kubernetes pods."""

    UNKNOWN = "UNKNOWN"
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    ERROR = "ERROR"
    DOWN = "DOWN"
    TERMINATING = "TERMINATING"
    TERMINATED = "TERMINATED"

    def __str__(self) -> str:
        return self.value

    @classmethod
    def from_string(cls, value: str) -> "PodStatus":
        """
        Create a PodStatus from a string value.

        Returns:
            PodStatus: The matching enum member.
        """
        return cls(value.upper())
