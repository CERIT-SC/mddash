from enum import Enum


class DeviceType(str, Enum):
    """GROMACS device types for PME and non-bonded calculations."""

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
