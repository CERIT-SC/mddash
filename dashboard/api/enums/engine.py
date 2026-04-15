from enum import Enum


class Engine(str, Enum):
    """Molecular dynamics engine types."""

    GMX = "gmx"
    AMBER = "amber"

    def __str__(self) -> str:
        return self.value

    @classmethod
    def from_string(cls, value: str) -> "Engine":
        """
        Create an Engine from a string value.

        Returns:
            Engine: The matching enum member.
        """
        # Case-insensitive lookup: compare lowercased value against lowercased member values
        value_lower = value.lower()
        for member in cls:
            if member.value.lower() == value_lower:
                return member
        # Fall back to standard constructor (will raise ValueError)
        return cls(value)


class AmberBinary(str, Enum):
    """AMBER binary types."""

    PMEMD_CUDA = "pmemd.cuda"
    PMEMD_MPI = "pmemd.MPI"

    def __str__(self) -> str:
        return self.value

    @classmethod
    def from_string(cls, value: str) -> "AmberBinary":
        """
        Create an AmberBinary from a string value.

        Returns:
            AmberBinary: The matching enum member.
        """
        # Case-insensitive lookup: compare lowercased value against lowercased member values
        value_lower = value.lower()
        for member in cls:
            if member.value.lower() == value_lower:
                return member
        # Fall back to standard constructor (will raise ValueError)
        return cls(value)


class EwaldPreset(str, Enum):
    """Ewald summation preset types."""

    DEFAULT = "default"
    OPTIMIZED = "optimized"

    def __str__(self) -> str:
        return self.value

    @classmethod
    def from_string(cls, value: str) -> "EwaldPreset":
        """
        Create an EwaldPreset from a string value.

        Returns:
            EwaldPreset: The matching enum member.
        """
        # Case-insensitive lookup: compare lowercased value against lowercased member values
        value_lower = value.lower()
        for member in cls:
            if member.value.lower() == value_lower:
                return member
        # Fall back to standard constructor (will raise ValueError)
        return cls(value)