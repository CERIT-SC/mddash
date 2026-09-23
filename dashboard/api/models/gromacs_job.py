import logging
import re
from datetime import UTC, datetime
from functools import cached_property
from pathlib import Path
from typing import TYPE_CHECKING, Any, ClassVar

from clients import mdrun
from config import DATA_DIR, S3_BUCKET
from enums import DeviceType, Engine, JobStatus
from extensions import db
from sqlalchemy import ForeignKey
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Mapped, mapped_column
from utils import nsteps_override, strip_run_control_args, tail, tail_bytes
from werkzeug.exceptions import (
    BadRequest,
    Forbidden,
    InternalServerError,
    NotFound,
    UnprocessableEntity,
)

from models.simulation import Simulation

from .simulation_job import SimulationJob

if TYPE_CHECKING:
    from .experiment import Experiment


logger = logging.getLogger(__name__)


class GromacsJob(SimulationJob):
    """GROMACS molecular dynamics simulation job."""

    __tablename__ = "gromacs_jobs"
    __mapper_args__: ClassVar[dict[str, Any]] = {"polymorphic_identity": Engine.GMX}

    # TODO: verify if files with these extensions should really be deleted
    RESULT_EXTENSIONS: ClassVar[list[str]] = ["edr", "gro", "log", "trr", "xtc", "cpt"]

    id: Mapped[str] = mapped_column(ForeignKey("simulation_jobs.id"), primary_key=True)

    # Device type for PME calculations
    pme: Mapped["DeviceType"] = mapped_column(db.Enum(DeviceType), nullable=False)
    # Device type for non-bonded interactions
    nb: Mapped["DeviceType"] = mapped_column(db.Enum(DeviceType), nullable=False)
    # Step at which the simulation started (non-zero when resuming from checkpoint)
    _init_step: Mapped[int | None] = mapped_column("init_step", db.Integer, nullable=True)

    @cached_property
    def _files(self) -> dict[str, str]:
        return Simulation.get(self.experiment_id, self.simulation_path).resolved_files

    @property
    def _run_input(self) -> str:
        return self._files["run_input"]

    @property
    def _deffnm(self) -> str:
        """Default filename without extension, derived from the TPR."""
        return self._run_input.removesuffix(".tpr")

    @property
    def _sim_dir(self) -> Path:
        """Experiment-relative directory containing the TPR (where the simulation runs)."""
        return Path(self._run_input).parent

    @property
    def _gmx_log(self) -> Path:
        """Path to the GROMACS log file."""
        return DATA_DIR / self.experiment_id / f"{self._deffnm}.log"

    @property
    def _stdout_log(self) -> Path:
        """Path to the stdout log file."""
        return DATA_DIR / self.experiment_id / self._sim_dir / f"mdrun-{self.id}.out"

    @property
    def _stderr_log(self) -> Path:
        """Path to the stderr log file."""
        return DATA_DIR / self.experiment_id / self._sim_dir / f"mdrun-{self.id}.err"

    @cached_property
    def _nsteps_override(self) -> int | None:
        """Production ``-nsteps`` override from the simulation's extra_args, if any."""
        return nsteps_override(Simulation.get(self.experiment_id, self.simulation_path).extra_args)

    @property
    def nsteps(self) -> int | None:
        """Total steps; a persisted value (extension target or log cache) outranks the manifest ``-nsteps`` override."""
        if self._archived or self._nsteps:
            return self._nsteps

        if override := self._nsteps_override:
            return override

        if val := self._parse_nsteps():
            self._nsteps = val
            db.session.commit()

        return self._nsteps

    @property
    def init_step(self) -> int:
        """Step at which the simulation started (0 for fresh runs, non-zero for checkpoint restarts)."""
        if self._archived or self._init_step is not None:
            return self._init_step or 0

        # 0 is a legitimate parse result — persist it so the full-log scan happens
        # only once per row instead of on every dump.
        if (val := self._parse_init_step()) is not None:
            self._init_step = val
            db.session.commit()

        return self._init_step or 0

    @property
    def estimated_time(self) -> int | None:
        """Estimated time until completion in seconds."""
        if self._archived or self.start_timestamp is None or self.nsteps is None or self.nsteps_done is None:
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
        simulation = Simulation.get(experiment.id, simulation_path)
        simulation.require_files(["run_input"])
        tpr_rel_path = simulation.resolved_files["run_input"]
        # TODO: remove as soon as user testing is done (also drop _nsteps below) — force all runs to 500k steps.
        extra_args = f"{strip_run_control_args(simulation.extra_args)} -nsteps 500000"

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
            _last_known_status=JobStatus.PENDING,  # type: ignore[call-arg]
            _nsteps=500000,  # type: ignore[call-arg]
        )
        db.session.add(job)

        job._cleanup_files()

        db.session.commit()
        simulation.mark_readonly()
        logger.info(f"Started GROMACS job {job.id} for experiment {experiment.id} (simulation {simulation_path})")

        return job

    @classmethod
    def extend(cls, experiment: "Experiment", simulation_path: str, nsteps: int) -> "GromacsJob":
        """
        Extend the latest segment by ``nsteps`` additional steps, resuming from its checkpoint.

        Raises:
            BadRequest: No prior segment, live segment, missing checkpoint, manifest contains ``-cpi``, or concurrent extend.
        """
        latest = cls.latest_for(experiment.id, simulation_path)
        if latest is None:
            raise BadRequest("No run exists for this simulation yet; extend requires a finished or stopped run.")
        if latest.is_live:
            raise BadRequest("The run is still active; stop it before extending.")

        simulation = Simulation.get(experiment.id, simulation_path)
        simulation.require_files(["run_input"])
        tpr_rel_path = simulation.resolved_files["run_input"]
        deffnm = tpr_rel_path.removesuffix(".tpr")

        checkpoint = DATA_DIR / experiment.id / f"{deffnm}.cpt"
        if not checkpoint.exists():
            raise BadRequest(
                f"No checkpoint file ({checkpoint.name}) found to resume from; it may still be syncing — try again shortly."
            )

        try:
            base_args = strip_run_control_args(simulation.extra_args)
        except ValueError as exc:
            raise BadRequest(str(exc)) from exc

        # Freeze log-derived fields before appending: parsers take the last match,
        # so the old segment's row must be locked before the new block is written.
        _ = latest.init_step, latest.start_timestamp, latest.performance
        previous_total = latest.nsteps
        if previous_total is None:
            raise BadRequest("Cannot determine the previous run's total step count from its log.")

        # Anchor on actual progress, not the previous target: a stopped segment
        # resumes from where it stood, so "extend by N" must mean N more steps
        # from that point (the same value is frozen for the history display).
        progress = latest.nsteps_done
        if progress is not None:
            latest.nsteps_done = progress
        base = progress if progress is not None else previous_total

        # mdrun -cpi counts -nsteps as ADDITIONAL steps from the checkpoint step —
        # a cumulative total here would over-run by all previous progress.
        total = base + nsteps
        cpt_name = f"{Path(tpr_rel_path).name.removesuffix('.tpr')}.cpt"
        extra_args = " ".join(filter(None, [base_args, f"-cpi {cpt_name}", f"-nsteps {nsteps}"]))

        mdrun_job = mdrun.create_job(
            experiment_id=experiment.id,
            tpr_name=tpr_rel_path,
            bucket_name=S3_BUCKET,
            pme=latest.pme.value,
            nb=latest.nb.value,
            np=latest.np,
            ntomp=latest.ntomp,
            extra_args=extra_args,
        )

        job = GromacsJob(
            id=mdrun_job["id"],  # type: ignore[call-arg]
            simulation_path=simulation_path,  # type: ignore[call-arg]
            pme=latest.pme,  # type: ignore[call-arg]
            nb=latest.nb,  # type: ignore[call-arg]
            np=latest.np,  # type: ignore[call-arg]
            ntomp=latest.ntomp,  # type: ignore[call-arg]
            experiment_id=experiment.id,  # type: ignore[call-arg]
            engine=Engine.GMX,  # type: ignore[call-arg]
            _last_known_status=JobStatus.PENDING,  # type: ignore[call-arg]
        )
        job._nsteps = total
        job._init_step = base
        db.session.add(job)
        try:
            db.session.commit()
        except IntegrityError:
            # Concurrent extend won the partial-unique-index race; clean up the orphaned cluster job.
            db.session.rollback()
            mdrun.delete_gmx_job(mdrun_job["id"])
            raise BadRequest("Another extension of this simulation is already in progress.") from None
        logger.info(
            f"Extended GROMACS simulation {simulation_path} (experiment {experiment.id}) "
            f"by {nsteps} steps to {total} as job {job.id}"
        )

        return job

    def _log_files(self) -> dict[str, Path]:
        """GROMACS log streams keyed by the log endpoint's ``type`` values."""
        return {"gmx": self._gmx_log, "stdout": self._stdout_log, "stderr": self._stderr_log}

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
            raise InternalServerError(description="System error reading log file.") from e

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
        """Last match wins — the log is appended across extensions, each segment dumps its own nsteps."""
        if not self._gmx_log.exists():
            return None

        result = None
        try:
            with self._gmx_log.open("r") as f:
                for line in f:
                    if "nsteps" not in line or "=" not in line:
                        continue

                    parts = line.split("=")
                    value = parts[-1].strip()
                    try:
                        result = int(value)
                    except ValueError:
                        continue

        except (FileNotFoundError, PermissionError, OSError, UnicodeDecodeError):
            logger.exception("Error reading nsteps from log file.")

        return result

    def _parse_init_step(self) -> int | None:
        """Return the initial step; last match wins since the log is appended across extensions."""
        if not self._gmx_log.exists():
            return None

        result = None
        try:
            with self._gmx_log.open("r") as f:
                for line in f:
                    if "init-step" not in line or "=" not in line:
                        continue

                    parts = line.split("=")
                    value = parts[-1].strip()
                    try:
                        result = int(value)
                    except ValueError:
                        continue

        except (FileNotFoundError, PermissionError, OSError, UnicodeDecodeError):
            logger.exception("Error reading init-step from log file.")

        return result

    def _parse_nsteps_done(self) -> int | None:
        """Return the steps completed so far, read from the tail of the engine log."""
        if not self._gmx_log.exists():
            return None

        try:
            log = tail_bytes(self._gmx_log)
            pattern = r"^\s*\d+\s+\d+\.\d+\s*"
            for line in reversed(log.splitlines()):
                # "Finished mdrun" may be from a prior segment; only trust it when
                # THIS job is FINISHED, else fall through to step rows.
                if "Finished mdrun" in line:
                    if self.status == JobStatus.FINISHED:
                        return self.nsteps
                    continue

                if not re.match(pattern, line):
                    continue

                parts = line.split()
                return int(parts[0])

        except (ValueError, FileNotFoundError, PermissionError, OSError, UnicodeDecodeError):
            logger.exception("Error reading nsteps_done from log file.")

        return None

    def _parse_start_timestamp(self) -> int | None:
        """Start timestamp; last match wins (newest segment's 'Started mdrun' line)."""
        if not self._gmx_log.exists():
            return None

        result = None
        try:
            with self._gmx_log.open("r") as f:
                for line in f:
                    if "Started mdrun" not in line:
                        continue

                    parts = line.split()
                    date_str = " ".join(parts[-5:])
                    dt = datetime.strptime(date_str, "%a %b %d %H:%M:%S %Y").replace(tzinfo=UTC)
                    result = int(dt.timestamp())

        except (ValueError, FileNotFoundError, PermissionError, OSError, UnicodeDecodeError):
            logger.exception("Error reading start time from log file.")

        return result

    def _parse_finish_timestamp(self) -> int | None:
        """Finish timestamp; last match in the appended log."""
        if not self._gmx_log.exists():
            return None

        try:
            log = tail_bytes(self._gmx_log)
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
        """Return performance in ns/day; last match wins (appended log)."""
        if not self._gmx_log.exists():
            return None

        try:
            log = tail_bytes(self._gmx_log)
            for line in reversed(log.splitlines()):
                if "Performance:" not in line:
                    continue

                parts = line.split()
                return float(parts[-2])

        except (ValueError, FileNotFoundError, PermissionError, OSError, UnicodeDecodeError):
            logger.exception("Error reading performance from log file.")
            return None

        return None
