from dataclasses import dataclass
from enum import Enum


class DeviceType(str, Enum):
    AUTO = "auto"
    CPU = "cpu"
    GPU = "gpu"

    def __str__(self):
        return self.value


class JobStatus(str, Enum):
    RUNNING = "RUNNING"
    PENDING = "PENDING"
    TERMINATED = "TERMINATED"
    ERROR = "ERROR"

    def __str__(self):
        return self.value


@dataclass
class GromacsJob:
    # unique ID of the job
    id: str
    # Status of the job
    status: JobStatus
    # Device type for PME calculations
    pme: DeviceType
    # Device type for non-bonded interactions
    nb: DeviceType
    # Number of MPI processes
    np: int
    # Number of OpenMP threads per MPI rank to start (0 is guess)
    ntomp: int
    # Extra arguments for the job
    extra_args: str
    # Performance (ns/day)
    performance: float
