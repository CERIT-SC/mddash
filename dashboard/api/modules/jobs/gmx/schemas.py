"""GROMACS run schemas."""

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field

from modules.jobs.schemas import PositiveInt, SimulationJob


class GromacsJob(SimulationJob):
    """GROMACS production run."""

    pme: Literal["auto", "cpu", "gpu"]
    nb: Literal["auto", "cpu", "gpu"]
    init_step: Annotated[int, Field(description="Step the run resumed from (0 for fresh runs)")] = 0


class GromacsJobRequest(BaseModel):
    """Compute settings for a GROMACS run."""

    model_config = ConfigDict(extra="forbid")

    np: PositiveInt
    ntomp: PositiveInt
    pme: Literal["cpu", "gpu"]
    nb: Literal["cpu", "gpu"]


class ExtendGromacsJobRequest(BaseModel):
    """Run extension."""

    model_config = ConfigDict(extra="forbid")

    # Steps to add on top of the current cumulative total (not the new total).
    nsteps: PositiveInt
