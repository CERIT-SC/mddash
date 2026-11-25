"""Population operation schemas."""

from typing import Literal

from core.enums import PopulationPhase, PopulationStatus
from core.schemas import OrmModel
from pydantic import BaseModel, ConfigDict

PopulationStatusValue = Literal["queued", "running", "cancelling", "succeeded", "failed", "cancelled"]
PopulationPhaseValue = Literal["starting", "crawling", "downloading", "finalizing", "cancelling"]


class PopulationJob(BaseModel):
    """Accepted Datahugger-NG population (202): identifiers for following the operation."""

    model_config = ConfigDict(extra="forbid")

    operation_id: str
    experiment_id: str


class Population(OrmModel):
    """Population lifecycle embedded in an ordinary Experiment response."""

    operation_id: str
    experiment_id: str
    status: PopulationStatus
    phase: PopulationPhase
    files_present: int
    files_total: int | None = None
    bytes_present: int
    bytes_total: int | None = None
    byte_percentage: float | None = None
    error: str | None = None
    renamed_paths: list[str] | None = None


class PopulationOperationStatus(BaseModel):
    """Read-only status of a Datahugger-NG population operation (legacy alias)."""

    model_config = ConfigDict(extra="forbid")

    operation_id: str
    experiment_id: str
    status: PopulationStatusValue
    phase: PopulationPhaseValue | None = None
    files_present: int = 0
    files_total: int | None = None
    bytes_present: int = 0
    bytes_total: int | None = None
    byte_percentage: float | None = None
    error: str | None = None
