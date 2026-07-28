"""Shared types across all engines."""

from enum import Enum

from pydantic import BaseModel, computed_field


class JobStatus(str, Enum):
    """Status of a tuning job or trial."""

    UNKNOWN = "UNKNOWN"
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    FINISHED = "FINISHED"
    ERROR = "ERROR"


class MDEngine(str, Enum):
    """Supported MD engine identifiers."""

    GMX = "gmx"
    AMBER = "amber"


class JobCreatedResponse(BaseModel):
    """Response for a newly created tuning job."""

    id: str
    status: JobStatus


class ResourcesResponse(BaseModel):
    """Ray cluster resource utilization."""

    total_cpus: int
    total_gpus: int
    available_cpus: int
    available_gpus: int

    @computed_field
    @property
    def used_cpus(self) -> int:
        """CPU cores currently in use."""
        return self.total_cpus - self.available_cpus

    @computed_field
    @property
    def used_gpus(self) -> int:
        """GPUs currently in use."""
        return self.total_gpus - self.available_gpus


class HealthResponse(BaseModel):
    """API liveness check response."""

    status: str
