from enum import Enum


class Step(str, Enum):
    """Wizard steps of a simulation; declaration order is display order, which clients derive counts from."""

    SETUP = "setup"
    CONFIGURATION = "configuration"
    SIMULATION = "simulation"
    ANALYSIS = "analysis"

    def __str__(self) -> str:
        return self.value
