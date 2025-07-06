from dataclasses import dataclass
from enum import Enum

from uuid import uuid4

from k8s import create_gromacs_job, delete_gromacs_job, get_job_status
from k8s_status import JobStatus
from config import NAMESPACE, DATA_DIR
from utils import tail


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
    # ID of the parent experiment
    experiment_id: str
    # Name of the TPR file
    tpr_name: str
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
    # Total steps of the job
    nsteps: int | None = None
    # Steps completed so far
    nsteps_done: int | None = None

    def start(self) -> None:
        """
        Start the job with the specified parameters.
        """
        try:
            deffnm = self.tpr_name.strip('.tpr')
            result_extensions = ['edr', 'gro', 'log', 'trr', 'xtc', 'cpt']

            # delete files from previous runs
            for ext in result_extensions:
                file = DATA_DIR / self.experiment_id / f'{deffnm}.{ext}'
                file.unlink(missing_ok=True)

            create_gromacs_job(
                ns=NAMESPACE,
                name=self.job_name,
                experiment_id=self.experiment_id,
                tpr_name=self.tpr_name,
                nb=self.nb,
                pme=self.pme,
                np=self.np,
                ntomp=self.ntomp,
                extra_args=self.extra_args
            )
        except Exception as e:
            print(f"Failed to start Gromacs job: {e}")
            self.status = JobStatus.ERROR

    def delete(self) -> None:
        """
        Delete the job and its associated resources.
        """
        try:
            # Delete the job from Kubernetes
            delete_gromacs_job(ns=NAMESPACE, name=self.job_name)
            
            # Delete log files
            (DATA_DIR / self.experiment_id / f'{self.job_name}.out').unlink(missing_ok=True)
            (DATA_DIR / self.experiment_id / f'{self.job_name}.err').unlink(missing_ok=True)
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

    def get_log(self, type: str = 'gmx', tail_lines: int = 100) -> str:
        """
        Get the log of the job.

        :param type: Type of log to retrieve (default is 'gmx')
        :param tail_lines: Number of lines to retrieve from the end of the log file
        :return: Log content as a string
        :raises ValueError: If the log type is invalid
        :raises FileNotFoundError: If the log file does not exist
        """
        deffnm = self.tpr_name.strip('.tpr')

        match type:
            case 'gmx':
                log_file = DATA_DIR / self.experiment_id / f'{deffnm}.log'
            case 'stdout':
                log_file = DATA_DIR / self.experiment_id / f'{self.job_name}.out'
            case 'stderr':
                log_file = DATA_DIR / self.experiment_id / f'{self.job_name}.err'
            case _:
                raise ValueError(f"Invalid log type: {type}")

        return tail(log_file, tail_lines)
