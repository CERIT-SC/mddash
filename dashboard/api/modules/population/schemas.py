"""Population operation schemas."""

from typing import Literal

from pydantic import BaseModel, ConfigDict

PopulationStatusValue = Literal["queued", "running", "succeeded", "failed"]


class PopulationJob(BaseModel):
    """Accepted Datahugger-NG population (202): identifiers for following the operation."""

    model_config = ConfigDict(extra="forbid")

    operation_id: str
    experiment_id: str


class PopulationOperationStatus(BaseModel):
    """Read-only status of a Datahugger-NG population operation."""

    model_config = ConfigDict(extra="forbid")

    operation_id: str
    experiment_id: str
    status: PopulationStatusValue
    error: str | None = None
