import re
import logging
from uuid import uuid4
from datetime import datetime
from typing import TYPE_CHECKING
from cachetools import cached, TTLCache
from sqlalchemy.orm import Mapped, mapped_column, relationship

from config import NAMESPACE, DATA_DIR, PVC_NAME
from clients import k8s
from utils import tail
from extensions import db

if TYPE_CHECKING:
    from enums import DeviceType, JobStatus
    from pathlib import Path
    from .experiment import Experiment


logger = logging.getLogger(__name__)

start_timestamp_cache: TTLCache = TTLCache(maxsize=100, ttl=0.5)  # 500ms
nsteps_cache: TTLCache = TTLCache(maxsize=100, ttl=0.5)  # 500ms
performance_cache: TTLCache = TTLCache(maxsize=100, ttl=0.5)  # 500ms
nsteps_done_cache: TTLCache = TTLCache(maxsize=100, ttl=1)  # 1s
estimated_time_cache: TTLCache = TTLCache(maxsize=100, ttl=0.5)  # 500ms


class GromacsJob(db.Model):  # type: ignore
    __tablename__ = 'gromacs_jobs'

    # TODO: verify if files with these extensions should really be deleted
    RESULT_EXTENSIONS = ['edr', 'gro', 'log', 'trr', 'xtc', 'cpt']

    # ID of the job inside the database
    id: Mapped[int] = mapped_column(db.Integer, primary_key=True)
    # ID of the experiment this job belongs to
    experiment_id: Mapped[str] = mapped_column(db.String(5), db.ForeignKey('experiments.id'))
    # creation time
    created_at: Mapped[datetime] = mapped_column(db.DateTime, default=datetime.now)
    # Name of the TPR file
    tpr_name: Mapped[str] = mapped_column(db.String(255), nullable=False)
    # Unique name of the k8s job
    job_name: Mapped[str] = mapped_column(db.String(255), nullable=False)
    # Device type for PME calculations
    pme: Mapped['DeviceType'] = mapped_column(db.Enum(DeviceType), nullable=False)
    # Device type for non-bonded interactions
    nb: Mapped['DeviceType'] = mapped_column(db.Enum(DeviceType), nullable=False)
    # Number of MPI processes
    np: Mapped[int] = mapped_column(db.Integer, nullable=False)
    # Number of OpenMP threads per MPI rank to start (0 is guess)
    ntomp: Mapped[int] = mapped_column(db.Integer, nullable=False)
    # Extra arguments for the job
    extra_args: Mapped[str] = mapped_column(db.Text, default='')
    
    # Unix timestamp when the job started
    _start_timestamp: Mapped[int | None] = mapped_column('start_timestamp', db.Integer, nullable=True)
    # Total steps of the job
    _nsteps: Mapped[int | None] = mapped_column('nsteps', db.Integer, nullable=True)
    # Performance (ns/day)
    _performance: Mapped[float | None] = mapped_column('performance', db.Float, nullable=True)

    # back-reference to the parent experiment
    experiment: Mapped['Experiment'] = relationship('Experiment', back_populates='gromacs_jobs')

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._init_paths()

    def _init_paths(self) -> None:
        """Initialize computed file paths."""
        self._deffnm = self.tpr_name.removesuffix('.tpr')
        base_dir = DATA_DIR / self.experiment_id
        self._gmx_log = base_dir / f'{self._deffnm}.log'
        self._stdout_log = base_dir / f'{self.job_name}.out'
        self._stderr_log = base_dir / f'{self.job_name}.err'

    @property
    def status(self) -> JobStatus:
        """Current status of the k8s job."""
        return k8s.get_job_status(ns=NAMESPACE, name=self.job_name)

    @property
    @cached(cache=nsteps_cache)
    def nsteps(self) -> int | None:
        """Total number of steps for the job."""
        if self._nsteps:
            return self._nsteps

        if val := self._parse_nsteps():
            self._nsteps = val
            db.session.commit()

        return self._nsteps

    @property
    @cached(cache=nsteps_done_cache)
    def nsteps_done(self) -> int | None:
        """Number of steps completed so far."""
        return self._parse_nsteps_done()

    @property
    @cached(cache=start_timestamp_cache)
    def start_timestamp(self) -> int | None:
        """Unix timestamp when the job started."""
        if self._start_timestamp:
            return self._start_timestamp

        if val := self._parse_start_timestamp():
            self._start_timestamp = val
            db.session.commit()

        return self._start_timestamp

    @property
    @cached(cache=estimated_time_cache)
    def estimated_time(self) -> int | None:
        """Estimated time until completion in seconds."""
        if self.start_timestamp is None or \
           self.nsteps is None or \
           self.nsteps_done is None or \
           self.nsteps_done == 0:
            return None

        remaining_steps = self.nsteps - self.nsteps_done

        if remaining_steps <= 0:
            return 0

        now = int(datetime.now().timestamp())
        time_per_step = (now - self.start_timestamp) / self.nsteps_done
        return int(remaining_steps * time_per_step)

    @property
    @cached(cache=performance_cache)
    def performance(self) -> float | None:
        """Performance of the job in ns/day."""
        if self._performance:
            return self._performance

        if val := self._parse_performance():
            self._performance = val
            db.session.commit()

        return self._performance

    @classmethod
    def start(cls, experiment: 'Experiment', tpr_path: Path, pme: DeviceType, nb: DeviceType, np: int, ntomp: int, extra_args: str = '') -> 'GromacsJob':
        """
        Start a tuner job for the given experiment and TPR file with specified parameters.
    
        :param experiment: The experiment to associate with the job.
        :param tpr_path: Path to the TPR file.
        :param pme: Device type for PME calculations.
        :param nb: Device type for non-bonded interactions.
        :param np: Number of MPI processes.
        :param ntomp: Number of OpenMP threads per MPI rank.
        :param extra_args: Additional arguments for the job.
        :return: The created GromacsJob instance.
        :raises Exception: If the job cannot be started.
        """
        job_name = f'gromacs-{uuid4()}'

        job = cls(
            tpr_name=tpr_path.name,
            job_name=job_name,
            pme=pme,
            nb=nb,
            np=np,
            ntomp=ntomp,
            extra_args=extra_args,
            experiment=experiment
        )

        job._cleanup_previous_results()

        k8s.create_gromacs_job(
            ns=NAMESPACE,
            pvc=PVC_NAME,
            name=job_name,
            experiment_id=experiment.id,
            deffnm=job._deffnm,
            nb=nb,
            pme=pme,
            np=np,
            ntomp=ntomp,
            extra_args=extra_args
        )

        db.session.add(job)
        db.session.commit()
        logger.info(f"Started GROMACS job {job_name} for experiment {experiment.id} with TPR {tpr_path.name}")
        
        return job

    def delete(self) -> None:
        """
        Delete the GROMACS job and its associated resources.

        :raises Exception: If the job cannot be deleted.
        """
        k8s.delete_job(ns=NAMESPACE, name=self.job_name)
        self._stdout_log.unlink(missing_ok=True)
        self._stderr_log.unlink(missing_ok=True)
        self._cleanup_previous_results()

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

    def _cleanup_previous_results(self) -> None:
        """
        Clean up previous results for this job.
        Deletes files with extensions defined in RESULT_EXTENSIONS.
        """
        for ext in self.RESULT_EXTENSIONS:
            file = DATA_DIR / self.experiment_id / f'{self._deffnm}.{ext}'
            if file.exists():
                file.unlink()
                logger.info(f"Deleted previous result file: {file}")

    def _parse_nsteps(self) -> int | None:
        """
        Get the total number of steps for the job.

        :return: Total number of steps or None if not available
        """
        try:
            with open(self._gmx_log, 'r') as f:
                for line in f:
                    if 'nsteps' not in line:
                        continue

                    parts = line.split('=')
                    return int(parts[-1].strip())

        except (FileNotFoundError, ValueError):
            logger.error(f"Error reading nsteps from log file.", exc_info=True)

        return None

    def _parse_nsteps_done(self) -> int | None:
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
                    return self.nsteps

                if not re.match(pattern, line):
                    continue

                parts = line.split()
                return int(parts[0])

        except (FileNotFoundError, ValueError):
            logger.error(f"Error reading nsteps_done from log file.", exc_info=True)

        return None

    def _parse_start_timestamp(self) -> int | None:
        """
        Get the start timestamp of the job.
        
        :return: Start timestamp or None if not available
        """
        try:
            with open(self._gmx_log, 'r') as f:
                for line in f:
                    if 'Started mdrun' not in line:
                        continue

                    parts = line.split()
                    date_str = ' '.join(parts[-5:])
                    dt = datetime.strptime(date_str, "%a %b %d %H:%M:%S %Y")
                    return int(dt.timestamp())

        except (FileNotFoundError, ValueError):
            logger.error(f"Error reading start time from log file.", exc_info=True)

        return None

    def _parse_performance(self) -> float | None:
        """
        Get the performance of the job in ns/day.
        
        :return: Performance in ns/day or None if not available
        """
        try:
            log = tail(self._gmx_log, 20)
            for line in reversed(log.splitlines()):
                if 'Performance:' not in line:
                    continue

                parts = line.split()
                return float(parts[-2])

        except (FileNotFoundError, ValueError):
            logger.error(f"Error reading performance from log file.", exc_info=True)
            return None

        return None
