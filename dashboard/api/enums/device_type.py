from enum import Enum


class DeviceType(str, Enum):
    """GROMACS device types for PME and non-bonded calculations."""

    AUTO = "auto"
    CPU = "cpu"
    GPU = "gpu"

    def __str__(self) -> str:
        """Return the string value of the device type."""
        return self.value

    @classmethod
    def from_string(cls, value: str) -> "DeviceType":
        """Create a DeviceType from a string value."""
        return cls(value.lower())
