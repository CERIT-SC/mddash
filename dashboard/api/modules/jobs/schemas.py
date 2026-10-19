"""Schemas shared by the production run engines (GROMACS, AMBER)."""

from datetime import datetime
from typing import Annotated, TypedDict

from core.enums import Engine, JobStatus
from core.schemas import OrmModel
from pydantic import ConfigDict, Field, with_config

PositiveInt = Annotated[int, Field(ge=1)]


@with_config(ConfigDict(extra="forbid"))
class SimulationJobLogLines(TypedDict, total=False):
    """Line counts per log stream for sizing badges without fetching logs; null while a stream's file does not exist yet."""

    gmx: Annotated[int | None, Field(description="Engine log (GROMACS only)")]
    mdout: Annotated[int | None, Field(description="Engine log (AMBER only)")]
    stdout: int | None
    stderr: int | None


class SimulationJob(OrmModel):
    """A production run of one simulation manifest (engine-specific fields pass through)."""

    model_config = ConfigDict(extra="allow")

    id: str
    experiment_id: str
    simulation_path: str
    created_at: datetime
    engine: Engine
    np: PositiveInt
    ntomp: PositiveInt
    status: JobStatus
    start_timestamp: int | None = None
    finish_timestamp: int | None = None
    nsteps: int | None = None
    nsteps_done: Annotated[int | None, Field(description="Steps completed so far (parsed from the engine log)")] = None
    performance: float | None = None
    estimated_time: Annotated[int | None, Field(description="Estimated seconds until completion")] = None
    # True while the job's status is non-terminal.
    is_live: bool
    log_lines: SimulationJobLogLines = Field(default_factory=dict)
