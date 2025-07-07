import re
from dataclasses import dataclass, field
from enum import Enum
from uuid import uuid4
from pathlib import Path

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
    # Number of MPI processes
    np: int
    # Number of OpenMP threads per MPI rank to start (0 is guess)
    ntomp: int
    # Device type for PME calculations
    pme: DeviceType
    # Device type for non-bonded interactions
    nb: DeviceType
    # Extra arguments for the job
    extra_args: str
    # Unique job name
    job_name: str = field(default_factory=lambda: f'gromacs-{uuid4()}')
    # Status of the job
    status: JobStatus = JobStatus.PENDING
    # Total steps of the job
    nsteps: int | None = None
    # Steps completed so far
    nsteps_done: int | None = None
    # Performance (ns/day)
    performance: float | None = None

    @property
    def _deffnm(self) -> str:
        return self.tpr_name.rstrip('.tpr')

    @property
    def _gmx_log(self) -> Path:
        return DATA_DIR / self.experiment_id / f'{self._deffnm}.log'

    @property
    def _stdout_log(self) -> Path:
        return DATA_DIR / self.experiment_id / f'{self.job_name}.out'

    @property
    def _stderr_log(self) -> Path:
        return DATA_DIR / self.experiment_id / f'{self.job_name}.err'

    def start(self) -> None:
        """
        Start the job with the specified parameters.
        """
        try:
            result_extensions = ['edr', 'gro', 'log', 'trr', 'xtc', 'cpt']

            # delete files from previous runs
            for ext in result_extensions:
                file = DATA_DIR / self.experiment_id / f'{self._deffnm}.{ext}'
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
            self._stdout_log.unlink(missing_ok=True)
            self._stderr_log.unlink(missing_ok=True)
        except Exception as e:
            print(f"Failed to stop Gromacs job: {e}")
            self.status = JobStatus.ERROR

    def poll_status(self) -> None:
        """
        Poll the status of the job.
        """
        try:
            self.status = get_job_status(ns=NAMESPACE, name=self.job_name)
            self.get_nsteps()
            self.get_nsteps_done()
            self.get_performance()
        except Exception as e:
            print(f"Failed to get Gromacs job status: {e}")
            self.status = JobStatus.ERROR

    def get_log(self, type: str = 'gmx', tail_lines: int | None = None) -> str:
        """
        Get the log of the job.

        :param type: Type of log to retrieve (default is 'gmx')
        :param tail_lines: Number of lines to retrieve from the end of the log file
        :return: Log content as a string
        :raises ValueError: If the log type is invalid
        :raises FileNotFoundError: If the log file does not exist
        """
        match type:
            case 'gmx':
                log_file = self._gmx_log
            case 'stdout':
                log_file = self._stdout_log
            case 'stderr':
                log_file = self._stderr_log
            case _:
                raise ValueError(f"Invalid log type: {type}")

        if tail_lines:
            return tail(log_file, tail_lines)
        else:
            with open(log_file, 'r') as f:
                return f.read()

    def get_nsteps(self) -> int | None:
        """
        Get the total number of steps for the job.

        :return: Total number of steps or None if not available
        """
        if self.nsteps is not None:
            return self.nsteps

        try:
            with open(self._gmx_log, 'r') as f:
                for line in f:
                    if 'nsteps' not in line:
                        continue

                    parts = line.split('=')
                    self.nsteps = int(parts[-1].strip())
                    return self.nsteps

        except (FileNotFoundError, ValueError) as e:
            print(f"Error reading nsteps from log file:", e)
            return None

        return None

    def get_nsteps_done(self) -> int | None:
        """
        Get the number of steps completed so far.

        :return: Number of steps completed or None if not available
        """
        try:
            log = tail(self._gmx_log, 20)
            pattern = r'^\s*\d+\s+\d+\.\d+\s*'
            for line in reversed(log.splitlines()):
                # if the simulation has finished, return the total steps
                if 'Finished mdrun' in line:
                    self.nsteps_done = self.get_nsteps()
                    return self.nsteps_done

                if not re.match(pattern, line):
                    continue

                parts = line.split()
                self.nsteps_done = int(parts[0])
                return self.nsteps_done

        except (FileNotFoundError, ValueError) as e:
            print(f"Error reading nsteps done from log file:", e)
            return None

        return None

    def get_performance(self) -> float | None:
        """
        Get the performance of the job in ns/day.

        :return: Performance in ns/day or None if not available
        """
        if self.performance is not None:
            return self.performance

        if self.status != JobStatus.TERMINATED:
            return None

        try:
            log = tail(self._gmx_log, 20)
            for line in reversed(log.splitlines()):
                if 'Performance:' not in line:
                    continue

                parts = line.split()
                self.performance = float(parts[-2])

        except (FileNotFoundError, ValueError) as e:
            print(f"Error reading performance from log file:", e)
            return None

        return None
