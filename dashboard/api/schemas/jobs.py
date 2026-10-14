"""Tuner, simulation (GROMACS/AMBER), and analysis job schemas."""

from datetime import datetime
from typing import Annotated, Literal, TypedDict

from enums import AnalysisType, Engine, JobStatus, PreprocessingMode
from pydantic import BaseModel, ConfigDict, Field, WithJsonSchema, with_config

from .common import OrmModel, enum_schema

AnalysisName = Annotated[AnalysisType, WithJsonSchema(enum_schema(AnalysisType))]
Preprocessing = Annotated[PreprocessingMode, WithJsonSchema(enum_schema(PreprocessingMode))]
PositiveInt = Annotated[int, Field(ge=1)]


@with_config(ConfigDict(extra="allow"))
class TunerTrial(TypedDict, total=False):
    """One tuning trial as reported by the tuner (engine-specific keys pass through)."""

    id: str
    status: JobStatus
    performance: float | None


class TunerJob(OrmModel):
    """Tuner job for one simulation manifest."""

    id: str
    experiment_id: str
    simulation_path: str
    nsteps: int
    error_message: str | None = None
    created_at: datetime
    is_stopped: bool
    engine: Engine
    tuner_status: JobStatus
    # True while the tuner job is not stopped and its status is non-terminal.
    is_live: bool
    sim_length_ns: float | None = None
    trials: list[TunerTrial]


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


class GromacsJob(SimulationJob):
    """GROMACS production run."""

    pme: Literal["auto", "cpu", "gpu"]
    nb: Literal["auto", "cpu", "gpu"]
    init_step: Annotated[int, Field(description="Step the run resumed from (0 for fresh runs)")] = 0


class AmberJob(SimulationJob):
    """AMBER production run."""

    binary: str
    ewald: str


class AnalysisJob(OrmModel):
    """On-demand mwf analysis job (input file paths pass through)."""

    model_config = ConfigDict(extra="allow")

    id: str
    experiment_id: str
    simulation_path: str
    analysis_name: AnalysisName
    created_at: datetime
    status: JobStatus
    sim_progress: Annotated[
        float | None,
        Field(
            description="Fraction (0-1) of the simulation's steps available when the analysis inputs were snapshotted; null when unknown."
        ),
    ] = None
    structure_file: str | None = None
    trajectory_file: str | None = None
    topology_file: str | None = None


class GromacsJobRequest(BaseModel):
    """Compute settings for a GROMACS run."""

    model_config = ConfigDict(extra="forbid")

    np: PositiveInt
    ntomp: PositiveInt
    pme: Literal["cpu", "gpu"]
    nb: Literal["cpu", "gpu"]


class AmberJobRequest(BaseModel):
    """Compute settings for an AMBER run."""

    model_config = ConfigDict(extra="forbid")

    binary: str
    ewald: str
    np: PositiveInt
    ntomp: PositiveInt


class ExtendGromacsJobRequest(BaseModel):
    """Run extension."""

    model_config = ConfigDict(extra="forbid")

    # Steps to add on top of the current cumulative total (not the new total).
    nsteps: PositiveInt


class TunerJobRequest(BaseModel):
    """Tuning job for a simulation manifest."""

    model_config = ConfigDict(extra="forbid")

    simulation_path: Annotated[str, Field(min_length=1)]
    nsteps: PositiveInt


class AnalysisJobRequest(BaseModel):
    """Analysis of a simulation's trajectory."""

    model_config = ConfigDict(extra="forbid")

    simulation_path: Annotated[str, Field(min_length=1)]
    analysis: AnalysisName
    preprocessing_mode: Preprocessing = PreprocessingMode.AS_IS


@with_config(ConfigDict(extra="allow"))
class AnalysisVariant(TypedDict):
    """One variant of a multi-file analysis (extra summary keys pass through)."""

    analysis: Annotated[str, Field(min_length=1)]
    name: Annotated[str, Field(min_length=1)]
