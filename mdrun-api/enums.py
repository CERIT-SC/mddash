from enum import Enum


class DeviceType(str, Enum):
    """Enumeration of device types for GROMACS computation."""

    AUTO = "auto"
    CPU = "cpu"
    GPU = "gpu"

    def __str__(self) -> str:
        return self.value

    @classmethod
    def from_string(cls, value: str) -> "DeviceType":
        """
        Create a DeviceType from a string value.

        Returns:
            DeviceType: The matching enum member.
        """
        return cls(value.lower())


class AmberBinary(str, Enum):
    """Enumeration of AMBER binary types."""

    PMEMD_CUDA = "pmemd.cuda"
    PMEMD_MPI = "pmemd.MPI"

    def __str__(self) -> str:
        return self.value

    @classmethod
    def from_string(cls, value: str) -> "AmberBinary":
        """
        Create an AmberBinary from a string value (case-insensitive).

        Returns:
            The matching enum member.
        """
        value_lower = value.lower()
        for member in cls:
            if member.value.lower() == value_lower:
                return member
        return cls(value)


class EwaldPreset(str, Enum):
    """Enumeration of Ewald summation presets for AMBER."""

    DEFAULT = "default"
    OPTIMIZED = "optimized"

    def __str__(self) -> str:
        return self.value

    @classmethod
    def from_string(cls, value: str) -> "EwaldPreset":
        """
        Create an EwaldPreset from a string value.

        Returns:
            The matching enum member.
        """
        return cls(value.lower())


class JobStatus(str, Enum):
    """Enumeration of possible job statuses."""

    PENDING = "pending"
    RUNNING = "running"
    FINISHED = "finished"
    ERROR = "error"
    UNKNOWN = "unknown"

    def __str__(self) -> str:
        return self.value
