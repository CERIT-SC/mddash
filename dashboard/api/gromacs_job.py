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
    # Unique ID of the job
    id: str
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
    # Status of the job
    status: JobStatus = JobStatus.PENDING
    # Performance (ns/day)
    performance: float | None = None

    def start(self) -> None:
        """
        Start the job with the specified parameters.
        """
        print(f"Starting Gromacs job...")
        # TODO

    def stop(self) -> None:
        """
        Stop the job.
        """
        print(f"Stopping Gromacs job...")
        # TODO

    def poll_status(self) -> None:
        """
        Poll the status of the job.
        """
        print(f"Polling status for Gromacs job...")
        # TODO
