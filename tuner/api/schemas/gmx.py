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
    # estimated wall-clock hours to run the full production simulation with this config
    estimated_time: float | None
    # estimated cost to run the full production simulation with this config
    estimated_cost: float | None


class GmxJobStatusResponse(BaseModel):
    """Full status response for a GMX tuning job."""

    id: str
    status: JobStatus
    error: str | None
    # full production simulation length (ns): from the original tpr, or the extra_args -nsteps override
    sim_length_ns: float | None
    trials: list[GmxTrialResponse]
