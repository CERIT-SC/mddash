"""Tuner job schemas."""

from datetime import datetime
from typing import Annotated, TypedDict

from core.enums import Engine, JobStatus
from core.schemas import OrmModel
from pydantic import BaseModel, ConfigDict, Field, with_config

from modules.jobs.schemas import PositiveInt


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


class TunerJobRequest(BaseModel):
    """Tuning job for a simulation manifest."""

    model_config = ConfigDict(extra="forbid")

    simulation_path: Annotated[str, Field(min_length=1)]
    nsteps: PositiveInt
