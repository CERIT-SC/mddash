from enum import Enum


class Engine(str, Enum):
    """Molecular dynamics engine types."""

    GMX = "GMX"
    AMBER = "AMBER"

    def __str__(self) -> str:
        return self.value

    @classmethod
    def from_string(cls, value: str) -> "Engine":
        """
        Create an Engine from a string value.

        Returns:
            Engine: The matching enum member.

        Raises:
            ValueError: If no matching engine is found.
        """
        # Case-insensitive lookup: legacy data may use lowercase
        value_upper = value.upper()
        for member in cls:
            if member.value == value_upper:
                return member
        raise ValueError(f"Invalid Engine: {value}")


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

        Raises:
            ValueError: If no matching binary is found.
        """
        # Case-insensitive lookup: inputs like 'PMEMD.CUDA' and 'pmemd.cuda' are equivalent
        value_lower = value.lower()
        for member in cls:
            if member.value.lower() == value_lower:
                return member
        raise ValueError(f"Invalid AmberBinary: {value}")


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
        return cls(value.lower())
