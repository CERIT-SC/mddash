from enum import Enum


class JobStatus(str, Enum):
    """Status values for all kinds of jobs."""

    UNKNOWN = "UNKNOWN"
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    FINISHED = "FINISHED"
    ERROR = "ERROR"
    STOPPED = "STOPPED"

    @property
    def is_live(self) -> bool:
        """Non-terminal states — the job may still advance without user action."""
        return self in {JobStatus.UNKNOWN, JobStatus.PENDING, JobStatus.RUNNING}

    @property
    def is_terminal(self) -> bool:
        """States that never change again — safe to cache and skip re-fetching."""
        return self in {JobStatus.FINISHED, JobStatus.ERROR, JobStatus.STOPPED}

    def __str__(self) -> str:
        return self.value

    @classmethod
    def from_string(cls, value: str) -> "JobStatus":
        """
        Create a JobStatus from a string value.

        Returns:
            JobStatus: The matching enum member.
        """
        return cls(value.upper())
