from enum import Enum


class JobStatus(str, Enum):
    """Status values for all kinds of jobs."""

    UNKNOWN = "UNKNOWN"
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    # MDRun/analysis jobs report TERMINATED on success.
    TERMINATED = "TERMINATED"
    # Tuner jobs and trials report FINISHED on success (successor of TERMINATED).
    FINISHED = "FINISHED"
    ERROR = "ERROR"

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
