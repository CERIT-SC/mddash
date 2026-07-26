"""GMX-specific response schemas."""

from pydantic import BaseModel

from api.schemas.common import JobStatus


class GmxTrialResponse(BaseModel):
    """Trial result for a GMX tuning job."""

    id: str
    status: JobStatus
    ntomp: int
    np: int
    nb: str
    pme: str
    performance: float | None


class GmxJobStatusResponse(BaseModel):
    """Full status response for a GMX tuning job."""

    id: str
    status: JobStatus
    error: str | None
    trials: list[GmxTrialResponse]
