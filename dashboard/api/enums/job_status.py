from enum import Enum


class JobStatus(str, Enum):
    """Status values for Kubernetes jobs."""

    UNKNOWN = "UNKNOWN"
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    TERMINATED = "TERMINATED"
    ERROR = "ERROR"

    def __str__(self) -> str:
        """Return the string value of the job status."""
        return self.value

    @classmethod
    def from_string(cls, value: str) -> "JobStatus":
        """Create a JobStatus from a string value."""
        return cls(value.upper())
