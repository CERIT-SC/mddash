import logging
import re
from datetime import UTC, datetime
from functools import cached_property
from pathlib import Path
from typing import TYPE_CHECKING, Any, ClassVar

from clients import mdrun
from config import DATA_DIR, S3_BUCKET
from enums import AmberBinary, Engine, EwaldPreset, JobStatus
from extensions import db
from sqlalchemy import ForeignKey
from sqlalchemy.orm import Mapped, mapped_column
from utils import tail
from werkzeug.exceptions import BadRequest, Forbidden, InternalServerError, NotFound, UnprocessableEntity

from models.simulation import Simulation

from .simulation_job import SimulationJob

if TYPE_CHECKING:
    from .experiment import Experiment


logger = logging.getLogger(__name__)


class AmberJob(SimulationJob):
    """AMBER molecular dynamics simulation job."""

    __tablename__ = "amber_jobs"
    __mapper_args__: ClassVar[dict[str, Any]] = {"polymorphic_identity": Engine.AMBER}

    RESULT_EXTENSIONS: ClassVar[list[str]] = ["nc", "rst7", "mdinfo", "out"]

    id: Mapped[str] = mapped_column(ForeignKey("simulation_jobs.id"), primary_key=True)

    # AMBER binary type
    binary: Mapped["AmberBinary"] = mapped_column(db.Enum(AmberBinary), nullable=False)
    # Ewald summation preset
    ewald: Mapped["EwaldPreset"] = mapped_column(db.Enum(EwaldPreset))

    @cached_property
    def _files(self) -> dict[str, str]:
        return Simulation.get(self.experiment_id, self.simulation_path).resolved_files

    @property
    def _mdin_path(self) -> Path:
        return DATA_DIR / self.experiment_id / self._files["control"]

    @property
    def _sim_dir(self) -> Path:
        """Experiment-relative directory containing the mdin (where the simulation runs)."""
        return Path(self._files["control"]).parent

    @property
    def _mdout_log(self) -> Path:
        base_name = Path(self._files["control"]).stem
        return DATA_DIR / self.experiment_id / self._sim_dir / f"{base_name}.out"

    @property
    def _mdinfo_log(self) -> Path:
        base_name = Path(self._files["control"]).stem
        return DATA_DIR / self.experiment_id / self._sim_dir / f"{base_name}.mdinfo"

    @property
    def _stdout_log(self) -> Path:
        """Path to the stdout log file."""
        return DATA_DIR / self.experiment_id / self._sim_dir / f"mdrun-{self.id}.out"

    @property
    def _stderr_log(self) -> Path:
        """Path to the stderr log file."""
        return DATA_DIR / self.experiment_id / self._sim_dir / f"mdrun-{self.id}.err"

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
    def nsteps_done(self) -> int | None:
        """Number of steps completed so far."""
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

        if self.status != JobStatus.FINISHED:
            return None

        if val := self._parse_finish_timestamp():
            self._finish_timestamp = val
            db.session.commit()

        return self._finish_timestamp

    @property
    def estimated_time(self) -> int | None:
        """Estimated time until completion in seconds."""
        if self.start_timestamp is None or self.nsteps is None or self.nsteps_done is None or self.nsteps_done == 0:
            return None

        remaining_steps = self.nsteps - self.nsteps_done
        if remaining_steps <= 0:
            return 0

        try:
            last_updated = self._mdinfo_log.stat().st_mtime
        except OSError:
            last_updated = datetime.now(UTC).timestamp()

        time_per_step = (last_updated - self.start_timestamp) / self.nsteps_done
        base_estimate = remaining_steps * time_per_step
        time_since_update = datetime.now(UTC).timestamp() - last_updated
        return max(0, int(base_estimate - time_since_update))

    @property
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
        binary: "AmberBinary",
        ewald: "EwaldPreset",
        np: int,
        ntomp: int,
    ) -> "AmberJob":
        """
        Start an AMBER job from a simulation manifest.

        Returns:
            The created AmberJob instance.
        """
        simulation = Simulation.get(experiment.id, simulation_path)
        simulation.require_files(["topology", "coordinates", "control"])
        resolved = simulation.resolved_files
        prmtop_rel_path = resolved["topology"]
        inpcrd_rel_path = resolved["coordinates"]
        mdin_rel_path = resolved["control"]
        extra_args = simulation.extra_args

        mdrun_job = mdrun.create_amber_job(
            experiment_id=experiment.id,
            prmtop_name=prmtop_rel_path,
            inpcrd_name=inpcrd_rel_path,
            mdin_name=mdin_rel_path,
            bucket_name=S3_BUCKET,
            binary=binary.value,
            ewald=ewald.value,
            np=np,
            ntomp=ntomp,
            extra_args=extra_args,
        )

        job = AmberJob(
            id=mdrun_job["id"],
            simulation_path=simulation_path,
            binary=binary,
            ewald=ewald,
            np=np,
            ntomp=ntomp,
            experiment_id=experiment.id,
            engine=Engine.AMBER,
        )
        db.session.add(job)

        job._cleanup_files()

        db.session.commit()
        simulation.mark_readonly()
        logger.info(f"Started AMBER job {job.id} for experiment {experiment.id} (simulation {simulation_path})")

        return job

    def _log_files(self) -> dict[str, Path]:
        """AMBER log streams keyed by the log endpoint's ``type`` values (mdinfo is progress state, not a stream)."""
        return {"mdout": self._mdout_log, "stdout": self._stdout_log, "stderr": self._stderr_log}

    def get_log(self, type: str = "mdout", tail_lines: int | None = None) -> str:
        """
        Get the log of the job.

        Args:
            type: Type of log to retrieve ('mdout', 'mdinfo', 'stdout', or 'stderr').
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
            case "mdout":
                log_file = self._mdout_log
            case "mdinfo":
                log_file = self._mdinfo_log
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
        base_name = Path(self._files["control"]).stem
        # Mirrors mdrun-api restart renaming: md.mdin + md.rst7 -> md_out.rst7.
        collision = Path(self._files["coordinates"]) == self._sim_dir / f"{base_name}.rst7"
        # Trajectory excluded: a previous run's output may legitimately sit there.
        inputs = {Path(path) for role, path in self._files.items() if path and role != "trajectory"}

        for ext in self.RESULT_EXTENSIONS:
            prefix = f"{base_name}_out" if ext == "rst7" and collision else base_name
            rel_path = self._sim_dir / f"{prefix}.{ext}"
            if rel_path in inputs:
                logger.info(f"Keeping manifest input file: {rel_path}")
                continue
            file = DATA_DIR / self.experiment_id / rel_path
            if file.exists():
                file.unlink()
                logger.info(f"Deleted previous result file: {file}")

        self._stdout_log.unlink(missing_ok=True)
        self._stderr_log.unlink(missing_ok=True)

    def _parse_nsteps(self) -> int | None:
        """
        Parse total steps from the nstlim parameter in the mdin file.

        Returns:
            Total number of steps or None if not available.
        """
        if not self._mdin_path.exists():
            return None

        try:
            with self._mdin_path.open("r") as f:
                for line in f:
                    match = re.search(r"nstlim\s*=\s*(\d+)", line, re.IGNORECASE)
                    if match:
                        return int(match.group(1))

        except (ValueError, FileNotFoundError, PermissionError, OSError, UnicodeDecodeError):
            logger.exception("Error reading nsteps from mdin file.")

        return None

    def _parse_nsteps_done(self) -> int | None:
        """
        Get the number of steps completed so far.

        Reads from mdinfo (updated in real-time by pmemd), falls back to mdout.

        Returns:
            Number of steps completed or None if not available.
        """
        if self._mdinfo_log.exists():
            try:
                log = tail(self._mdinfo_log, 20)
                match = re.search(r"Nstep\s*=\s*(\d+)", log, re.IGNORECASE)
                if match:
                    return int(match.group(1))
            except (ValueError, FileNotFoundError, PermissionError, OSError, UnicodeDecodeError):
                logger.exception("Error reading nsteps_done from mdinfo file.")

        # Fall back to mdout for completed jobs where mdinfo may be gone
        if not self._mdout_log.exists():
            return None

        try:
            log = tail(self._mdout_log, 200)
            last_match = None
            for line in log.splitlines():
                match = re.search(r"^\s*NSTEP\s*=\s*(\d+)", line)
                if match:
                    last_match = int(match.group(1))

            if last_match is not None:
                return last_match

        except (ValueError, FileNotFoundError, PermissionError, OSError, UnicodeDecodeError):
            logger.exception("Error reading nsteps_done from mdout file.")

        return None

    def _parse_performance(self) -> float | None:
        """
        Get the performance of the job in ns/day.

        Returns:
            Performance in ns/day or None if not available.
        """
        if not self._mdout_log.exists():
            return None

        try:
            log = tail(self._mdout_log, 50)
            pattern = r"ns/day\s*=\s*([\d.]+)"
            for line in reversed(log.splitlines()):
                match = re.search(pattern, line)
                if match:
                    return float(match.group(1))

        except (ValueError, FileNotFoundError, PermissionError, OSError, UnicodeDecodeError):
            logger.exception("Error reading performance from mdout file.")
            return None

        return None

    def _parse_start_timestamp(self) -> int | None:
        """
        Parse the start timestamp from the mdout file.

        AMBER writes: "| Run on MM/DD/YYYY at HH:MM:SS"

        Returns:
            Start timestamp or None if not available.
        """
        if not self._mdout_log.exists():
            return None

        try:
            with self._mdout_log.open("r") as f:
                for line in f:
                    if "Run on" not in line:
                        continue

                    match = re.search(r"Run on\s+(\d{2}/\d{2}/\d{4})\s+at\s+(\d{2}:\d{2}:\d{2})", line)
                    if match:
                        dt = datetime.strptime(
                            f"{match.group(1)} {match.group(2)}",
                            "%m/%d/%Y %H:%M:%S",
                        ).replace(tzinfo=UTC)
                        return int(dt.timestamp())

        except (ValueError, FileNotFoundError, PermissionError, OSError, UnicodeDecodeError):
            logger.exception("Error reading start time from mdout file.")

        return None

    def _parse_finish_timestamp(self) -> int | None:
        """
        Compute the finish timestamp from mdout file.

        AMBER does not write an explicit completion line. We derive the finish
        time by parsing the "Master Total wall time" and adding it to the start
        timestamp. Falls back to the mdout file's mtime.

        Returns:
            Finish timestamp or None if not available.
        """
        if not self._mdout_log.exists() or not self.start_timestamp:
            return None

        try:
            log = tail(self._mdout_log, 30)
            for line in reversed(log.splitlines()):
                if "Master Total wall time" not in line:
                    continue

                # Format: "|  Master Total wall time:       1094    seconds     0.30 hours"
                match = re.search(r"Master Total wall time:\s+(\d+)\s+seconds", line)
                if match:
                    return self.start_timestamp + int(match.group(1))

        except (ValueError, FileNotFoundError, PermissionError, OSError, UnicodeDecodeError):
            logger.exception("Error reading finish time from mdout file.")

        # Fall back to file modification time
        try:
            return int(self._mdout_log.stat().st_mtime)
        except OSError:
            return None
