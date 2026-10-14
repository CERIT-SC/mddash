"""Simulation manifest schemas."""

from typing import Annotated, Any

from enums import Engine
from pydantic import BaseModel, BeforeValidator, ConfigDict, Field


def _string_roles(value: Any) -> Any:  # ruff:ignore[any-type]
    """Hand-edited manifests may hold non-string role values; those are reported as errors, not echoed."""
    if isinstance(value, dict):
        return {role: path for role, path in value.items() if isinstance(path, str)}
    return value


type SimulationFiles = dict[str, Annotated[str, Field(min_length=1)]]
ManifestFiles = Annotated[SimulationFiles, BeforeValidator(_string_roles)]


class SimulationWrite(BaseModel):
    """Simulation manifest content to create or update."""

    model_config = ConfigDict(extra="forbid")

    simulation_path: str | None = None
    name: Annotated[str, Field(min_length=1)]
    engine: Engine | None = None
    files: SimulationFiles
    extra_args: str = ""


class Simulation(BaseModel):
    """A simulation manifest with its validation, lock, and wizard state."""

    model_config = ConfigDict(extra="forbid")

    simulation_path: str
    name: str
    engine: str
    files: ManifestFiles
    resolved_files: ManifestFiles
    extra_args: str
    locked: bool
    valid: bool
    errors: list[str]
    missing_files: list[str]
    # Wizard phase index (Setup 0, Tune 1, Run 2, Analyze 3); publish is experiment-level.
    step: Annotated[int, Field(ge=0, le=3)]
    status: str
    # True while any tuner or production job for this simulation may still advance on its own.
    live: bool
    last_activity: float
