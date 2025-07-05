from dataclasses import dataclass
from enum import Enum

from uuid import uuid4

from k8s import create_gromacs_job, delete_gromacs_job, get_job_status
from k8s_status import JobStatus
from config import NAMESPACE, DATA_DIR


class DeviceType(str, Enum):
    AUTO = "auto"
    CPU = "cpu"
    GPU = "gpu"

    def __str__(self):
        return self.value
    
    @classmethod
    def from_string(cls, value: str) -> 'DeviceType':
        return cls(value.lower())


@dataclass
class GromacsJob:
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
    # Unique job name
    job_name: str = f'gromacs-{uuid4()}'
    # Status of the job
    status: JobStatus = JobStatus.PENDING
    # Performance (ns/day)
    performance: float | None = None

    def start(self, experiment_id: str, tpr_name: str) -> None:
        """
        Start the job with the specified parameters.

        :param experiment_id: ID of the experiment
        :param tpr_name: Name of the TPR file
        """
        try:
            deffnm = tpr_name.strip('.tpr')
            result_extensions = ['edr', 'gro', 'log', 'trr', 'xtc', 'cpt']

            # delete files from previous runs
            for ext in result_extensions:
                file = DATA_DIR / experiment_id / f'{deffnm}.{ext}'
                file.unlink(missing_ok=True)

            create_gromacs_job(
                ns=NAMESPACE,
                name=self.job_name,
                experiment_id=experiment_id,
                tpr_name=tpr_name,
                nb=self.nb,
                pme=self.pme,
                np=self.np,
                ntomp=self.ntomp,
                extra_args=self.extra_args
            )
        except Exception as e:
            print(f"Failed to start Gromacs job: {e}")
            self.status = JobStatus.ERROR

    def stop(self) -> None:
        """
        Stop the job.
        """
        try:
            delete_gromacs_job(ns=NAMESPACE, name=self.job_name)
        except Exception as e:
            print(f"Failed to stop Gromacs job: {e}")
            self.status = JobStatus.ERROR

    def poll_status(self) -> None:
        """
        Poll the status of the job.
        """
        try:
            self.status = get_job_status(ns=NAMESPACE, name=self.job_name)
        except Exception as e:
            print(f"Failed to get Gromacs job status: {e}")
            self.status = JobStatus.ERROR

        # TODO
        # - get progress from log
        # - get performance (after job completion)
