"""AMBER-specific response schemas."""

from pydantic import BaseModel

from api.schemas.common import JobStatus


class AmberTrialResponse(BaseModel):
    """Trial result for an AMBER tuning job."""

    id: str
    status: JobStatus
    binary: str
    np: int
    ntomp: int
    ewald: str
    performance: float | None


class AmberJobStatusResponse(BaseModel):
    """Full status response for an AMBER tuning job."""

    id: str
    status: JobStatus
    error: str | None
    trials: list[AmberTrialResponse]
