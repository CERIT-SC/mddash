import logging
import shlex
import shutil
import uuid
from contextlib import suppress
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Self

import anyio
import sqlalchemy as sa
from cache import analysis_status_cache
from clients import k8s
from clients.k8s import parse_cpu, parse_memory
from config import ANALYSIS_IMAGE, ANALYSIS_RESOURCES, DATA_DIR
from db import Base
from enums import AnalysisType, Engine, JobStatus, PreprocessingMode
from errors import Forbidden
from sqlalchemy import Select, select
from sqlalchemy.orm import Mapped, mapped_column, relationship, selectinload

from .simulation_job import SimulationJob

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from .experiment import Experiment


logger = logging.getLogger(__name__)

ANALYSIS_RESULT_PREFIX = "mda."
ANALYSIS_RESULT_SUFFIX = ".json"
MWF_DIR = "analysis/mwf"
MWF_INPUTS_DIR = "analysis/mwf/inputs"
MWF_INCOMPLETE_PREFIX = "incomplete_"


def mwf_output_dir(simulation_path: str) -> str:
    """
    Per-simulation MWF output directory, e.g. analysis/mwf/protein.

    Returns:
        MWF output subdirectory path relative to the experiment dir.
    """
    stem = Path(simulation_path).stem
    return f"{MWF_DIR}/{stem}"


AUTO_INTERACTION_ANALYSES = {
    AnalysisType.DIST,
    AnalysisType.ENERGIES,
    AnalysisType.HBONDS,
    AnalysisType.INTER,
}
ANALYSIS_RUNTIME_PREP_TASKS = {
    AnalysisType.CLUSTERS: ("clusters",),
    AnalysisType.DIST: ("inter",),
    AnalysisType.ENERGIES: ("inter",),
    AnalysisType.HBONDS: ("inter",),
    AnalysisType.INTER: ("inter",),
}


def get_incomplete_task_dirs(task_name: str) -> list[Path]:
    """
    Build plausible incomplete-task directories for a third-party mwf task.

    Args:
        task_name: The mwf task flag, such as ``inter`` or ``clusters``.

    Returns:
        Candidate project-relative and MD-relative incomplete task directories.
    """
    incomplete_dir = f"{MWF_INCOMPLETE_PREFIX}{task_name}"
    return [Path(incomplete_dir)]


def get_analysis_runtime_prep_commands(analysis_name: AnalysisType) -> list[str]:
    """
    Build analysis-specific shell prep for known third-party mwf quirks.

    Args:
        analysis_name: The requested mwf analysis.

    Returns:
        Extra shell commands needed before invoking mwf for this analysis.
    """
    task_names = ANALYSIS_RUNTIME_PREP_TASKS.get(analysis_name, ())
    if not task_names:
        return []

    temp_dirs: list[Path] = []
    for task_name in task_names:
        temp_dirs.extend(get_incomplete_task_dirs(task_name))

    # Preserve declaration order while removing duplicates.
    unique_temp_dirs = list(dict.fromkeys(path.as_posix() for path in temp_dirs))
    mkdir_args = " ".join(shlex.quote(path) for path in unique_temp_dirs)
    return [f"mkdir -p {mkdir_args}"]


def find_result_file(experiment_id: str, simulation_path: str, name: str) -> Path | None:
    """
    Find a result file by normalized name under the simulation's mwf output directory.

    Returns:
        The first matching Path, or None if not found.
    """
    filename = f"{ANALYSIS_RESULT_PREFIX}{name.replace('-', '_')}{ANALYSIS_RESULT_SUFFIX}"
    mwf_dir = DATA_DIR / experiment_id / mwf_output_dir(simulation_path)
    if not mwf_dir.is_dir():
        return None
    matches = list(mwf_dir.rglob(filename))
    return matches[0] if matches else None


def list_result_files(experiment_id: str, simulation_path: str) -> list[Path]:
    """
    List all mda.*.json result files under the simulation's mwf output directory.

    Returns:
        Sorted list of matching Paths, or empty list if directory doesn't exist.
    """
    mwf_dir = DATA_DIR / experiment_id / mwf_output_dir(simulation_path)
    if not mwf_dir.is_dir():
        return []
    return sorted(mwf_dir.rglob(f"{ANALYSIS_RESULT_PREFIX}*{ANALYSIS_RESULT_SUFFIX}"))


def get_runtime_prelude_commands(analysis_name: AnalysisType) -> list[str]:
    """
    Build shell commands that prepare the third-party mwf container runtime.

    Args:
        analysis_name: The requested mwf analysis.

    Returns:
        Shell commands that should run before invoking mwf.
    """
    commands = [
        'export HOME="$PWD/.mddash-home"',
        'mkdir -p "$HOME"',
        "git config --global --add safe.directory /app/MDDB-workflow >/dev/null 2>&1 || true",
    ]
    commands.extend(get_analysis_runtime_prep_commands(analysis_name))
    return commands


def format_mwf_inputs_yaml(analysis_name: AnalysisType) -> str:
    """
    Build the minimal inputs.yaml content for an analysis job.

    Args:
        analysis_name: The requested mwf analysis.

    Returns:
        The YAML content passed to mwf as inputs.yaml.
    """
    lines = ["name: mddash", "type: trajectory", "pbc_selection: auto"]
    if analysis_name in AUTO_INTERACTION_ANALYSES:
        lines.extend(["interactions:", "  - auto"])
    return "\n".join(lines) + "\n"


def _safe_copy(src: Path, dst: Path) -> str:
    src_q = shlex.quote(src.as_posix())
    dst_q = shlex.quote(dst.as_posix())
    return f"[ {src_q} -ef {dst_q} ] || cp {src_q} {dst_q}"


def format_mwf_analysis_command(
    analysis_name: AnalysisType,
    structure_file: Path | None,
    trajectory_file: Path,
    topology_file: Path | None,
    preprocessing_mode: PreprocessingMode,
    simulation_path: str,
    engine: Engine = Engine.GMX,
) -> str:
    """
    Build the mwf command for a single analysis job.

    When structure_file is absent, omit the -stru flag so mwf derives the
    structure from the topology + trajectory itself (required for AMBER .prmtop
    which has no coordinates).

    AMBER trajectories are typically un-imaged, so stable-bonds checking is
    skipped via -t stabonds to avoid spurious failures.

    Returns:
        Shell command string used to execute the requested mwf analysis.

    Raises:
        ValueError: If both structure_file and topology_file are None.
    """
    if structure_file is None and topology_file is None:
        raise ValueError("At least one of structure_file or topology_file must be provided.")

    trajectory_snapshot = Path(MWF_INPUTS_DIR) / f"input_trajectory{trajectory_file.suffix}"
    topology_snapshot = Path(MWF_INPUTS_DIR) / f"input_topology{topology_file.suffix}" if topology_file else None

    snapshot_commands: list[str] = [
        _safe_copy(trajectory_file, trajectory_snapshot),
    ]

    # -stru only when a separate structure file is provided
    stru_flag = ""
    if structure_file is not None:
        structure_snapshot = Path(MWF_INPUTS_DIR) / f"input_structure{structure_file.suffix}"
        snapshot_commands.insert(0, _safe_copy(structure_file, structure_snapshot))
        stru_flag = f"-stru {shlex.quote(structure_snapshot.as_posix())} "

    if topology_file and topology_snapshot:
        snapshot_commands.append(_safe_copy(topology_file, topology_snapshot))

    flags = [f"-top {shlex.quote(topology_snapshot.as_posix())}" if topology_snapshot else "-top no"]
    if preprocessing_mode in {PreprocessingMode.IMAGE, PreprocessingMode.IMAGE_FIT}:
        flags.append("-img")
    if preprocessing_mode is PreprocessingMode.IMAGE_FIT:
        flags.append("-fit")

    # AMBER topologies often have non-standard residues or bonds that mwf
    # considers "incoherent"; skip both checks that are overzealous for AMBER.
    trust_flags = "-t stabonds cohbonds" if engine is Engine.AMBER else ""

    inputs_yaml = shlex.quote(format_mwf_inputs_yaml(analysis_name))
    prelude_commands = get_runtime_prelude_commands(analysis_name)
    output_dir = mwf_output_dir(simulation_path)

    commands = [
        f"mkdir -p {shlex.quote(MWF_INPUTS_DIR)} {shlex.quote(output_dir)}",
        *prelude_commands,
        *snapshot_commands,
        f"printf %s {inputs_yaml} > inputs.yaml",
        "conda run --no-capture-output -n mwf_env "
        f"mwf run -dir . {stru_flag}"
        f"-md {shlex.quote(output_dir)} {shlex.quote(trajectory_snapshot.as_posix())} "
        f"{' '.join(flags)} -i {analysis_name} {trust_flags}",
    ]
    return " && ".join(commands)


class AnalysisJob(Base):
    """On-demand MD analysis job running mddb-workflow in a K8s Job."""

    __tablename__ = "analysis_jobs"

    id: Mapped[str] = mapped_column(sa.String(36), primary_key=True)
    experiment_id: Mapped[str] = mapped_column(sa.String(5), sa.ForeignKey("experiments.id"))
    simulation_path: Mapped[str] = mapped_column(sa.String(255), nullable=False)
    created_at: Mapped[datetime] = mapped_column(sa.DateTime, default=lambda: datetime.now(UTC))

    analysis_name: Mapped[AnalysisType] = mapped_column(sa.Enum(AnalysisType), nullable=False)
    structure_file: Mapped[str | None] = mapped_column(sa.String(255), nullable=True)
    trajectory_file: Mapped[str] = mapped_column(sa.String(255), nullable=False)
    topology_file: Mapped[str | None] = mapped_column(sa.String(255), nullable=True)
    # Fraction of the simulation's steps available when the analysis inputs were
    # snapshotted; None when the run progress was unknown (or no run existed).
    sim_progress: Mapped[float | None] = mapped_column(sa.Float, nullable=True)

    _last_known_status: Mapped[JobStatus | None] = mapped_column("last_known_status", sa.Enum(JobStatus), nullable=True)

    # Never lazy-loads (async); queries for jobs alone load it via `query()`.
    experiment: Mapped["Experiment"] = relationship("Experiment", back_populates="analysis_jobs", lazy="raise_on_sql")

    # Transient: status fetched by refresh_status() for this request
    _fetched_status: JobStatus | None = None

    @classmethod
    def query(cls) -> "Select[tuple[Self]]":
        """Select analysis jobs together with their experiments."""
        return select(cls).options(selectinload(cls.experiment))

    @property
    def _job_name(self) -> str:
        return f"analysis-{self.id}"

    @property
    def _settled_status(self) -> JobStatus | None:
        """FINISHED or ERROR once reached: such a job never changes again."""
        status = self._last_known_status
        return status if status in {JobStatus.FINISHED, JobStatus.ERROR} else None

    async def refresh_status(self) -> JobStatus:
        """Fetch the K8s Job status (short TTL cache); a finished job's temp files are cleaned once."""
        if settled := self._settled_status:
            self._fetched_status = settled
            return settled

        try:
            fetched = analysis_status_cache.get(self.id)
            if fetched is None:
                fetched = await k8s.get_job_status(self._job_name)
                analysis_status_cache[self.id] = fetched
            if fetched not in {self._last_known_status, JobStatus.UNKNOWN}:
                self._last_known_status = fetched
                if fetched == JobStatus.FINISHED:
                    await anyio.to_thread.run_sync(self.cleanup_temp_files)
        except Exception:
            logger.exception(f"Error fetching analysis job status for {self.id}")
            fetched = self._last_known_status or JobStatus.UNKNOWN

        self._fetched_status = fetched
        return fetched

    @property
    def status(self) -> JobStatus:
        """
        Current status of the K8s job, as of the last `refresh_status()`.

        Raises:
            RuntimeError: If an unsettled job was not refreshed in this request.
        """
        if settled := self._settled_status:
            return settled
        if self._fetched_status is None:
            raise RuntimeError(f"Status of analysis job {self.id} read before refresh_status()")
        return self._fetched_status

    @classmethod
    async def start(
        cls,
        session: "AsyncSession",
        experiment: "Experiment",
        simulation_path: str,
        analysis_name: AnalysisType,
        structure_file: Path | None,
        trajectory_file: Path,
        topology_file: Path | None,
        preprocessing_mode: PreprocessingMode,
    ) -> "AnalysisJob":
        """
        Start an analysis K8s Job for a single analysis type, replacing the simulation's previous analyses.

        Args:
            session: The request's database session.
            experiment: The experiment to run analysis on.
            simulation_path: The simulation manifest path this analysis belongs to.
            analysis_name: The mwf analysis task name (e.g. "rmsds", "pca").
            structure_file: Structure file within the experiment dir; None when the topology serves as structure.
            trajectory_file: Trajectory file within the experiment dir.
            topology_file: Topology file, when required for preprocessing or analysis.
            preprocessing_mode: Selected preprocessing mode applied before analysis.

        Raises:
            Forbidden: If the job cannot be started due to insufficient cluster resources.
        """
        previous_jobs = [j for j in experiment.analysis_jobs if j.simulation_path == simulation_path]
        for prev in previous_jobs:
            with suppress(Exception):  # job may already be cleaned up by K8s
                await k8s.delete_job(f"analysis-{prev.id}")
            await anyio.to_thread.run_sync(prev.cleanup_temp_files)
            await session.delete(prev)
        await session.flush()

        job_id = str(uuid.uuid4())[:12]
        job_name = f"analysis-{job_id}"

        # Snapshot the run's progress now: the inputs copied at job start are
        # exactly the data this analysis will cover.
        run_job = (
            (
                await session.execute(
                    SimulationJob
                    .query()
                    .filter_by(experiment_id=experiment.id, simulation_path=simulation_path)
                    .order_by(SimulationJob.created_at.desc())
                )
            )
            .scalars()
            .first()
        )
        sim_progress: float | None = None
        if run_job is not None:
            await run_job.refresh_status()
            nsteps, done = await anyio.to_thread.run_sync(lambda: (run_job.nsteps, run_job.nsteps_done))
            if nsteps is not None and nsteps > 0 and done is not None:
                sim_progress = min(1.0, done / nsteps)

        command = format_mwf_analysis_command(
            analysis_name=analysis_name,
            structure_file=structure_file,
            trajectory_file=trajectory_file,
            topology_file=topology_file,
            preprocessing_mode=preprocessing_mode,
            simulation_path=simulation_path,
            engine=experiment.engine,
        )

        an_cpu = parse_cpu(ANALYSIS_RESOURCES["requests"]["cpu"])
        an_mem = parse_memory(ANALYSIS_RESOURCES["requests"]["memory"])
        an_cpu_limit = parse_cpu(ANALYSIS_RESOURCES["limits"]["cpu"])
        an_mem_limit = parse_memory(ANALYSIS_RESOURCES["limits"]["memory"])
        if msg := await k8s.check_quota_headroom(an_cpu, an_mem, an_cpu_limit, an_mem_limit):
            raise Forbidden(f"Cannot start analysis: {msg}")

        await k8s.create_job(
            name=job_name,
            image=ANALYSIS_IMAGE,
            experiment_id=experiment.id,
            command=command,
            resources=ANALYSIS_RESOURCES,
        )

        job = AnalysisJob(
            id=job_id,
            experiment_id=experiment.id,
            experiment=experiment,
            simulation_path=simulation_path,
            analysis_name=analysis_name,
            structure_file=structure_file.as_posix() if structure_file else None,
            trajectory_file=trajectory_file.as_posix(),
            topology_file=topology_file.as_posix() if topology_file else None,
            sim_progress=sim_progress,
        )
        session.add(job)
        await session.commit()

        logger.info(f"Started analysis job {job_id} ({analysis_name}) for experiment {experiment.id}")
        return job

    def cleanup_temp_files(self) -> None:
        """Remove temporary files left in the experiment directory by a job run."""
        exp_dir = DATA_DIR / self.experiment_id

        with suppress(Exception):
            (exp_dir / "inputs.yaml").unlink()

        with suppress(Exception):
            shutil.rmtree(exp_dir / MWF_INPUTS_DIR)

        task_names = ANALYSIS_RUNTIME_PREP_TASKS.get(self.analysis_name, ())
        for task_name in task_names:
            for incomplete_dir in get_incomplete_task_dirs(task_name):
                with suppress(Exception):
                    shutil.rmtree(exp_dir / incomplete_dir)

        mwf_dir = exp_dir / mwf_output_dir(self.simulation_path)
        if mwf_dir.is_dir():
            result_pattern = f"{ANALYSIS_RESULT_PREFIX}*{ANALYSIS_RESULT_SUFFIX}"
            for path in mwf_dir.rglob("*"):
                if path.is_file() and not path.match(result_pattern):
                    with suppress(Exception):
                        path.unlink()
            # bottom-up so inner empty dirs are removed before their parents
            for path in sorted(mwf_dir.rglob("*"), reverse=True):
                if path.is_dir():
                    with suppress(Exception):
                        path.rmdir()

    async def delete(self) -> None:
        """Delete the K8s job and clean up any temporary files it left behind (the caller deletes the row)."""
        await k8s.delete_job(self._job_name)
        await anyio.to_thread.run_sync(self.cleanup_temp_files)
