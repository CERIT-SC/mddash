from enum import Enum


class JobStatus(str, Enum):
    """Status values for all kinds of jobs."""

    UNKNOWN = "UNKNOWN"
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    TERMINATED = "TERMINATED"
    ERROR = "ERROR"

    def __str__(self) -> str:
        """
        Return the string value of the job status.

        Returns:
            str: The string value of this enum member.
        """
        return self.value

    @classmethod
    def from_string(cls, value: str) -> "JobStatus":
        """
        Create a JobStatus from a string value.

        Returns:
            JobStatus: The matching enum member.
        """
        return cls(value.upper())
