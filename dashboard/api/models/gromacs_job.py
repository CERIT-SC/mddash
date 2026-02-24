import logging
import re
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, ClassVar

from cache import (
    gromacs_estimated_time_cache,
    gromacs_nsteps_done_cache,
    gromacs_performance_cache,
    gromacs_status_cache,
)
from cachetools import cached
from clients import mdrun
from config import DATA_DIR, S3_BUCKET
from enums import DeviceType, JobStatus
from extensions import db
from sqlalchemy.orm import Mapped, mapped_column, relationship
from utils import tail
from werkzeug.exceptions import (
    BadRequest,
    Forbidden,
    InternalServerError,
    NotFound,
    UnprocessableEntity,
)

if TYPE_CHECKING:
    from .experiment import Experiment


logger = logging.getLogger(__name__)


class GromacsJob(db.Model):  # type: ignore
    """GROMACS molecular dynamics simulation job."""

    __tablename__ = "gromacs_jobs"

    # TODO: verify if files with these extensions should really be deleted
    RESULT_EXTENSIONS: ClassVar[list[str]] = ["edr", "gro", "log", "trr", "xtc", "cpt", "fit.xtc"]

    # ID of the job inside the database
    id: Mapped[str] = mapped_column(db.String(36), primary_key=True)
    # ID of the experiment this job belongs to
    experiment_id: Mapped[str] = mapped_column(db.String(5), db.ForeignKey("experiments.id"))
    # creation time
    created_at: Mapped[datetime] = mapped_column(db.DateTime, default=datetime.now)
    # Name of the TPR file
    tpr_name: Mapped[str] = mapped_column(db.String(255), nullable=False)
    # Device type for PME calculations
    pme: Mapped["DeviceType"] = mapped_column(db.Enum(DeviceType), nullable=False)
    # Device type for non-bonded interactions
    nb: Mapped["DeviceType"] = mapped_column(db.Enum(DeviceType), nullable=False)
    # Number of MPI processes
    np: Mapped[int] = mapped_column(db.Integer, nullable=False)
    # Number of OpenMP threads per MPI rank to start (0 is guess)
    ntomp: Mapped[int] = mapped_column(db.Integer, nullable=False)
    # Extra arguments for the job
    extra_args: Mapped[str] = mapped_column(db.Text, default="")

    # Unix timestamp when the job started
    _start_timestamp: Mapped[int | None] = mapped_column("start_timestamp", db.Integer, nullable=True)
    # Unix timestamp when the job finished
    _finish_timestamp: Mapped[int | None] = mapped_column("finish_timestamp", db.Integer, nullable=True)
    # Total steps of the job
    _nsteps: Mapped[int | None] = mapped_column("nsteps", db.Integer, nullable=True)
    # Performance (ns/day)
    _performance: Mapped[float | None] = mapped_column("performance", db.Float, nullable=True)

    # back-reference to the parent experiment
    experiment: Mapped["Experiment"] = relationship("Experiment", back_populates="gromacs_jobs")

    @property
    def _deffnm(self) -> str:
        """Default filename without extension."""
        return self.tpr_name.removesuffix(".tpr")

    @property
    def _gmx_log(self) -> Path:
        """Path to the GROMACS log file."""
        return DATA_DIR / self.experiment_id / f"{self._deffnm}.log"

    @property
    def _stdout_log(self) -> Path:
        """Path to the stdout log file."""
        return DATA_DIR / self.experiment_id / f"mdrun-{self.id}.out"

    @property
    def _stderr_log(self) -> Path:
        """Path to the stderr log file."""
        return DATA_DIR / self.experiment_id / f"mdrun-{self.id}.err"

    @property
    @cached(cache=gromacs_status_cache)
    def status(self) -> JobStatus:
        """Current status of the k8s job."""
        try:
            return JobStatus.from_string(mdrun.get_job(self.id)["status"])
        except Exception:
            logger.exception(f"Error fetching job status for job {self.id}")
            return JobStatus.UNKNOWN

    @property
    def nsteps(self) -> int | None:
        """Total number of steps for the job."""
        if self._nsteps:
            return self._nsteps

        if val := self._parse_nsteps():
            self._nsteps = val
            db.session.commit()

        return self._nsteps

    @property
    @cached(cache=gromacs_nsteps_done_cache)
    def nsteps_done(self) -> int | None:
        """Number of steps completed so far."""
        # If simulation has finished, return total steps
        if self._performance:
            return self._nsteps

        return self._parse_nsteps_done()

    @property
    def start_timestamp(self) -> int | None:
        """Unix timestamp when the job started."""
        if self._start_timestamp:
            return self._start_timestamp

        if val := self._parse_start_timestamp():
            self._start_timestamp = val
            db.session.commit()

        return self._start_timestamp

    @property
    def finish_timestamp(self) -> int | None:
        """Unix timestamp when the job finished."""
        if self._finish_timestamp:
            return self._finish_timestamp

        if self.status != JobStatus.TERMINATED:
            return None

        if val := self._parse_finish_timestamp():
            self._finish_timestamp = val
            db.session.commit()

        return self._finish_timestamp

    @property
    @cached(cache=gromacs_estimated_time_cache)
    def estimated_time(self) -> int | None:
        """Estimated time until completion in seconds."""
        if self.start_timestamp is None or self.nsteps is None or self.nsteps_done is None or self.nsteps_done == 0:
            return None

        remaining_steps = self.nsteps - self.nsteps_done
        if remaining_steps <= 0:
            return 0

        try:
            last_updated = self._gmx_log.stat().st_mtime
        except OSError:
            last_updated = datetime.now().timestamp()

        time_per_step = (last_updated - self.start_timestamp) / self.nsteps_done
        base_estimate = remaining_steps * time_per_step
        time_since_update = datetime.now().timestamp() - last_updated
        return max(0, int(base_estimate - time_since_update))

    @property
    @cached(cache=gromacs_performance_cache)
    def performance(self) -> float | None:
        """Performance of the job in ns/day."""
        if self._performance:
            return self._performance

        if val := self._parse_performance():
            self._performance = val
            db.session.commit()

        return self._performance

    @classmethod
    def start(
        cls,
        experiment: "Experiment",
        tpr_path: Path,
        pme: DeviceType,
        nb: DeviceType,
        np: int,
        ntomp: int,
        extra_args: str = "",
    ) -> "GromacsJob":
        """
        Start a GROMACS job for the given experiment and TPR file.

        Args:
            experiment: The experiment to associate with the job.
            tpr_path: Path to the TPR file.
            pme: Device type for PME calculations.
            nb: Device type for non-bonded interactions.
            np: Number of MPI processes.
            ntomp: Number of OpenMP threads per MPI rank.
            extra_args: Additional arguments for the job.

        Returns:
            The created GromacsJob instance.

        Raises:
            Exception: If the job cannot be started.
        """
        mdrun_job = mdrun.create_job(
            experiment_id=experiment.id,
            tpr_name=tpr_path.name,
            bucket_name=S3_BUCKET,
            pme=pme.value,
            nb=nb.value,
            np=np,
            ntomp=ntomp,
            extra_args=extra_args,
        )

        job = GromacsJob(
            id=mdrun_job["id"],  # type: ignore[call-arg]
            tpr_name=tpr_path.name,  # type: ignore[call-arg]
            pme=pme,  # type: ignore[call-arg]
            nb=nb,  # type: ignore[call-arg]
            np=np,  # type: ignore[call-arg]
            ntomp=ntomp,  # type: ignore[call-arg]
            extra_args=extra_args,  # type: ignore[call-arg]
            experiment_id=experiment.id,  # type: ignore[call-arg]
        )
        db.session.add(job)

        job._cleanup_previous_results()

        db.session.commit()
        logger.info(f"Started GROMACS job {job.id} for experiment {experiment.id} with TPR {tpr_path.name}")

        return job

    def delete(self) -> None:
        """
        Delete the GROMACS job and its associated resources.

        Raises:
            Exception: If the job cannot be deleted.
        """
        mdrun.delete_job(self.id)
        self._stdout_log.unlink(missing_ok=True)
        self._stderr_log.unlink(missing_ok=True)
        self._cleanup_previous_results()

    def get_log(self, type: str = "gmx", tail_lines: int | None = None) -> str:
        """
        Get the log of the job.

        Args:
            type: Type of log to retrieve (default is 'gmx').
            tail_lines: Number of lines to retrieve from the end of the log file.

        Returns:
            Log content as a string.

        Raises:
            HTTPException: If the log type is invalid or the log file cannot be accessed.
        """
        match type:
            case "gmx":
                log_file = self._gmx_log
            case "stdout":
                log_file = self._stdout_log
            case "stderr":
                log_file = self._stderr_log
            case _:
                raise BadRequest(description=f"Invalid log type: {type}")

        try:
            if tail_lines:
                return tail(log_file, tail_lines)
            with log_file.open("r") as f:
                return f.read()
        except FileNotFoundError:
            raise NotFound(description=f"Log file not found: {log_file.name}")
        except PermissionError:
            raise Forbidden(description=f"Permission denied accessing log file: {log_file.name}")
        except UnicodeDecodeError:
            raise UnprocessableEntity(description=f"Unable to decode log file: {log_file.name}")
        except OSError as e:
            raise InternalServerError(description=f"System error reading log file: {e}")

    def _cleanup_previous_results(self) -> None:
        """
        Clean up previous results for this job.

        Deletes files with extensions defined in RESULT_EXTENSIONS.
        """
        for ext in self.RESULT_EXTENSIONS:
            file = DATA_DIR / self.experiment_id / f"{self._deffnm}.{ext}"
            if file.exists():
                file.unlink()
                logger.info(f"Deleted previous result file: {file}")

    def _parse_nsteps(self) -> int | None:
        """
        Get the total number of steps for the job.

        Returns:
            Total number of steps or None if not available.
        """
        if not self._gmx_log.exists():
            return None

        try:
            with self._gmx_log.open("r") as f:
                for line in f:
                    if "nsteps" not in line:
                        continue

                    parts = line.split("=")
                    return int(parts[-1].strip())

        except (ValueError, FileNotFoundError, PermissionError, OSError, UnicodeDecodeError):
            logger.exception("Error reading nsteps from log file.")

        return None

    def _parse_nsteps_done(self) -> int | None:
        """
        Get the number of steps completed so far.

        Returns:
            Number of steps completed or None if not available.
        """
        if not self._gmx_log.exists():
            return None

        try:
            log = tail(self._gmx_log, 20)
            pattern = r"^\s*\d+\s+\d+\.\d+\s*"
            for line in reversed(log.splitlines()):
                # if the simulation has finished, return the total steps
                if "Finished mdrun" in line:
                    return self.nsteps

                if not re.match(pattern, line):
                    continue

                parts = line.split()
                return int(parts[0])

        except (ValueError, FileNotFoundError, PermissionError, OSError, UnicodeDecodeError):
            logger.exception("Error reading nsteps_done from log file.")

        return None

    def _parse_start_timestamp(self) -> int | None:
        """
        Get the start timestamp of the job.

        Returns:
            Start timestamp or None if not available.
        """
        if not self._gmx_log.exists():
            return None

        try:
            with self._gmx_log.open("r") as f:
                for line in f:
                    if "Started mdrun" not in line:
                        continue

                    parts = line.split()
                    date_str = " ".join(parts[-5:])
                    dt = datetime.strptime(date_str, "%a %b %d %H:%M:%S %Y")
                    return int(dt.timestamp())

        except (ValueError, FileNotFoundError, PermissionError, OSError, UnicodeDecodeError):
            logger.exception("Error reading start time from log file.")

        return None

    def _parse_finish_timestamp(self) -> int | None:
        """
        Get the finish timestamp of the job.

        Returns:
            Finish timestamp or None if not available.
        """
        if not self._gmx_log.exists():
            return None

        try:
            log = tail(self._gmx_log, 10)
            for line in reversed(log.splitlines()):
                if "Finished mdrun" not in line:
                    continue

                parts = line.split()
                date_str = " ".join(parts[-5:])
                dt = datetime.strptime(date_str, "%a %b %d %H:%M:%S %Y")
                return int(dt.timestamp())

        except (ValueError, FileNotFoundError, PermissionError, OSError, UnicodeDecodeError):
            logger.exception("Error reading finish time from log file.")

        return None

    def _parse_performance(self) -> float | None:
        """
        Get the performance of the job in ns/day.

        Returns:
            Performance in ns/day or None if not available.
        """
        if not self._gmx_log.exists():
            return None

        try:
            log = tail(self._gmx_log, 20)
            for line in reversed(log.splitlines()):
                if "Performance:" not in line:
                    continue

                parts = line.split()
                return float(parts[-2])

        except (ValueError, FileNotFoundError, PermissionError, OSError, UnicodeDecodeError):
            logger.exception("Error reading performance from log file.")
            return None

        return None
