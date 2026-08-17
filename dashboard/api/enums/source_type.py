from enum import Enum


class SourceType(str, Enum):
    """How an experiment's structure source was created."""

    PDB = "pdb"
    REPO = "repo"
    FILE = "file"

    def __str__(self) -> str:
        return self.value
