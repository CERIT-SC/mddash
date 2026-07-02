import logging
import re
from datetime import UTC, datetime
from functools import cached_property
from pathlib import Path
from typing import TYPE_CHECKING, Any, ClassVar

from cache import (
    gromacs_estimated_time_cache,
    gromacs_nsteps_done_cache,
    gromacs_performance_cache,
)
from cachetools import cached
from clients import mdrun
from config import DATA_DIR, S3_BUCKET
from enums import DeviceType, Engine, JobStatus
from extensions import db
from sqlalchemy import ForeignKey
from sqlalchemy.orm import Mapped, mapped_column
from utils import tail
from werkzeug.exceptions import (
    BadRequest,
    Forbidden,
    InternalServerError,
    NotFound,
    UnprocessableEntity,
)

from models.simulation import (
    get_simulation,
    mark_simulation_readonly,
    simulation_files,
    validate_simulation_for_action,
)

from .simulation_job import SimulationJob

if TYPE_CHECKING:
    from .experiment import Experiment


logger = logging.getLogger(__name__)


class GromacsJob(SimulationJob):
    """GROMACS molecular dynamics simulation job."""

    __tablename__ = "gromacs_jobs"
    __mapper_args__: ClassVar[dict[str, Any]] = {"polymorphic_identity": Engine.GMX}

    # TODO: verify if files with these extensions should really be deleted
    RESULT_EXTENSIONS: ClassVar[list[str]] = ["edr", "gro", "log", "trr", "xtc", "cpt", "fit.xtc"]

    id: Mapped[str] = mapped_column(ForeignKey("simulation_jobs.id"), primary_key=True)

    # Device type for PME calculations
    pme: Mapped["DeviceType"] = mapped_column(db.Enum(DeviceType), nullable=False)
    # Device type for non-bonded interactions
    nb: Mapped["DeviceType"] = mapped_column(db.Enum(DeviceType), nullable=False)
    # Step at which the simulation started (non-zero when resuming from checkpoint)
    _init_step: Mapped[int | None] = mapped_column("init_step", db.Integer, nullable=True)

    @cached_property
    def _files(self) -> dict[str, str]:
        return simulation_files(self.experiment_id, self.simulation_path)

    @property
    def _topology_rel(self) -> str:
        return self._files["topology"]

    @property
    def _deffnm(self) -> str:
        """Default filename without extension, derived from the simulation topology."""
        return self._topology_rel.removesuffix(".tpr")

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
    def nsteps(self) -> int | None:
        """Total number of steps for the job."""
        if self._nsteps:
            return self._nsteps

        if val := self._parse_nsteps():
            self._nsteps = val
            db.session.commit()

        return self._nsteps

    @property
    def init_step(self) -> int:
        """Step at which the simulation started (0 for fresh runs, non-zero for checkpoint restarts)."""
        if self._init_step is not None:
            return self._init_step

        if val := self._parse_init_step():
            self._init_step = val
            db.session.commit()

        return self._init_step or 0

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
        if self.start_timestamp is None or self.nsteps is None or self.nsteps_done is None:
            return None

        remaining_steps = self.nsteps - self.nsteps_done
        if remaining_steps <= 0:
            return 0

        steps_done_in_run = self.nsteps_done - self.init_step
        if steps_done_in_run <= 0:
            return None

        try:
            last_updated = self._gmx_log.stat().st_mtime
        except OSError:
            last_updated = datetime.now(UTC).timestamp()

        time_per_step = (last_updated - self.start_timestamp) / steps_done_in_run
        base_estimate = remaining_steps * time_per_step
        time_since_update = datetime.now(UTC).timestamp() - last_updated
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
        simulation_path: str,
        pme: DeviceType,
        nb: DeviceType,
        np: int,
        ntomp: int,
    ) -> "GromacsJob":
        """
        Start a GROMACS job for the given experiment and simulation manifest.

        The TPR path and ``extra_args`` are derived from the simulation JSON and
        passed to MDRun; only ``simulation_path`` and compute settings are persisted.

        Args:
            experiment: The experiment to associate with the job.
            simulation_path: Experiment-relative path to the ``.simulation.json``.
            pme: Device type for PME calculations.
            nb: Device type for non-bonded interactions.
            np: Number of MPI processes.
            ntomp: Number of OpenMP threads per MPI rank.

        Returns:
            The created GromacsJob instance.
        """
        simulation = get_simulation(experiment.id, simulation_path)
        validate_simulation_for_action(simulation, "run")
        tpr_rel_path = simulation["resolved_files"]["topology"]
        extra_args = simulation.get("extra_args", "")

        mdrun_job = mdrun.create_job(
            experiment_id=experiment.id,
            tpr_name=tpr_rel_path,
            bucket_name=S3_BUCKET,
            pme=pme.value,
            nb=nb.value,
            np=np,
            ntomp=ntomp,
            extra_args=extra_args,
        )

        job = GromacsJob(
            id=mdrun_job["id"],  # type: ignore[call-arg]
            simulation_path=simulation_path,  # type: ignore[call-arg]
            pme=pme,  # type: ignore[call-arg]
            nb=nb,  # type: ignore[call-arg]
            np=np,  # type: ignore[call-arg]
            ntomp=ntomp,  # type: ignore[call-arg]
            experiment_id=experiment.id,  # type: ignore[call-arg]
            engine=Engine.GMX,  # type: ignore[call-arg]
        )
        db.session.add(job)

        job._cleanup_files()

        db.session.commit()
        mark_simulation_readonly(experiment.id, simulation_path)
        logger.info(f"Started GROMACS job {job.id} for experiment {experiment.id} (simulation {simulation_path})")

        return job

    def get_log(self, type: str = "gmx", tail_lines: int | None = None) -> str:
        """
        Get the log of the job.

        Args:
            type: Type of log to retrieve (default is 'gmx').
            tail_lines: Number of lines to retrieve from the end of the log file.

        Returns:
            Log content as a string.

        Raises:
            BadRequest: If the log type is invalid.
            NotFound: If the log file does not exist.
            Forbidden: If access to the log file is denied.
            UnprocessableEntity: If the log file cannot be decoded.
            InternalServerError: If a system error occurs while reading the log file.
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

    def _cleanup_files(self) -> None:
        """
        Clean up files associated with this GROMACS job.

        Deletes files with extensions defined in RESULT_EXTENSIONS and removes
        stdout/stderr log files.
        """
        for ext in self.RESULT_EXTENSIONS:
            file = DATA_DIR / self.experiment_id / f"{self._deffnm}.{ext}"
            if file.exists():
                file.unlink()
                logger.info(f"Deleted previous result file: {file}")

        self._stdout_log.unlink(missing_ok=True)
        self._stderr_log.unlink(missing_ok=True)

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
                    if "nsteps" not in line or "=" not in line:
                        continue

                    parts = line.split("=")
                    value = parts[-1].strip()
                    try:
                        return int(value)
                    except ValueError:
                        continue

        except (FileNotFoundError, PermissionError, OSError, UnicodeDecodeError):
            logger.exception("Error reading nsteps from log file.")

        return None

    def _parse_init_step(self) -> int | None:
        """
        Get the initial step of the job (non-zero when resuming from a checkpoint).

        Returns:
            Initial step or None if not available.
        """
        if not self._gmx_log.exists():
            return None

        try:
            with self._gmx_log.open("r") as f:
                for line in f:
                    if "init-step" not in line or "=" not in line:
                        continue

                    parts = line.split("=")
                    value = parts[-1].strip()
                    try:
                        return int(value)
                    except ValueError:
                        continue

        except (FileNotFoundError, PermissionError, OSError, UnicodeDecodeError):
            logger.exception("Error reading init-step from log file.")

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
                    dt = datetime.strptime(date_str, "%a %b %d %H:%M:%S %Y").replace(tzinfo=UTC)
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
                dt = datetime.strptime(date_str, "%a %b %d %H:%M:%S %Y").replace(tzinfo=UTC)
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
