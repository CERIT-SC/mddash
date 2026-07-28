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
    # estimated wall-clock hours to run the full production simulation with this config
    estimated_time: float | None
    # estimated cost to run the full production simulation with this config
    estimated_cost: float | None


class AmberJobStatusResponse(BaseModel):
    """Full status response for an AMBER tuning job."""

    id: str
    status: JobStatus
    error: str | None
    # full production simulation length (ns) extracted from the original mdin
    sim_length_ns: float | None
    trials: list[AmberTrialResponse]
