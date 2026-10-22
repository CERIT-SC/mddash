"""AMBER run schemas."""

from pydantic import BaseModel, ConfigDict

from modules.jobs.schemas import PositiveInt, SimulationJob


class AmberJob(SimulationJob):
    """AMBER production run."""

    binary: str
    ewald: str


class AmberJobRequest(BaseModel):
    """Compute settings for an AMBER run."""

    model_config = ConfigDict(extra="forbid")

    binary: str
    ewald: str
    np: PositiveInt
    ntomp: PositiveInt
