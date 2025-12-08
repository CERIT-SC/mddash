from enum import Enum


class DeviceType(str, Enum):
    """Enumeration of device types for GROMACS computation."""

    AUTO = "auto"
    CPU = "cpu"
    GPU = "gpu"

    def __str__(self) -> str:
        """Return the string value of the enum."""
        return self.value

    @classmethod
    def from_string(cls, value: str) -> "DeviceType":
        """Create a DeviceType from a string value."""
        return cls(value.lower())


class JobStatus(str, Enum):
    """Enumeration of possible job statuses."""

    PENDING = "pending"
    RUNNING = "running"
    TERMINATED = "terminated"
    ERROR = "error"
    UNKNOWN = "unknown"

    def __str__(self) -> str:
        """Return the string value of the enum."""
        return self.value
