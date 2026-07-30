import logging
import shlex
import shutil
import uuid
from contextlib import suppress
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING

from cache import analysis_status_cache
from cachetools import cached
from clients import k8s
from clients.k8s import parse_cpu, parse_memory
from config import ANALYSIS_IMAGE, ANALYSIS_RESOURCES, DATA_DIR
from enums import AnalysisType, Engine, JobStatus, PreprocessingMode
from extensions import db
from sqlalchemy.orm import Mapped, mapped_column, relationship
from werkzeug.exceptions import Forbidden

if TYPE_CHECKING:
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


class AnalysisJob(db.Model):  # type: ignore
    """On-demand MD analysis job running mddb-workflow in a K8s Job."""

    __tablename__ = "analysis_jobs"

    id: Mapped[str] = mapped_column(db.String(36), primary_key=True)
    experiment_id: Mapped[str] = mapped_column(db.String(5), db.ForeignKey("experiments.id"))
    simulation_path: Mapped[str] = mapped_column(db.String(255), nullable=False)
    created_at: Mapped[datetime] = mapped_column(db.DateTime, default=lambda: datetime.now(UTC))

    analysis_name: Mapped[AnalysisType] = mapped_column(db.Enum(AnalysisType), nullable=False)
    structure_file: Mapped[str | None] = mapped_column(db.String(255), nullable=True)
    trajectory_file: Mapped[str] = mapped_column(db.String(255), nullable=False)
    topology_file: Mapped[str | None] = mapped_column(db.String(255), nullable=True)

    _last_known_status: Mapped[JobStatus | None] = mapped_column("last_known_status", db.Enum(JobStatus), nullable=True)

    experiment: Mapped["Experiment"] = relationship("Experiment", back_populates="analysis_jobs")

    @property
    def _job_name(self) -> str:
        return f"analysis-{self.id}"

    @property
    @cached(cache=analysis_status_cache)
    def status(self) -> JobStatus:
        """Current status of the K8s job."""
        if self._last_known_status is not None and self._last_known_status in {JobStatus.FINISHED, JobStatus.ERROR}:
            return self._last_known_status

        try:
            fetched = k8s.get_job_status(self._job_name)
            if fetched not in {self._last_known_status, JobStatus.UNKNOWN}:
                self._last_known_status = fetched
                db.session.commit()
                if fetched == JobStatus.FINISHED:
                    self.cleanup_temp_files()
            return fetched
        except Exception:
            logger.exception(f"Error fetching analysis job status for {self.id}")
            if self._last_known_status:
                return self._last_known_status
            return JobStatus.UNKNOWN

    @classmethod
    def start(
        cls,
        experiment: "Experiment",
        simulation_path: str,
        analysis_name: AnalysisType,
        structure_file: Path | None,
        trajectory_file: Path,
        topology_file: Path | None,
        preprocessing_mode: PreprocessingMode,
    ) -> "AnalysisJob":
        """
        Start an analysis K8s Job for a single analysis type.

        Args:
            experiment: The experiment to run analysis on.
            simulation_path: The simulation manifest path this analysis belongs to.
            analysis_name: The mwf analysis task name (e.g. "rmsds", "pca").
            structure_file: Relative path to the structure file within the experiment dir.
                May be None when topology_file serves as the structure source.
            trajectory_file: Relative path to the trajectory file within the experiment dir.
            topology_file: Relative path to the topology file, when required for preprocessing or analysis.
            preprocessing_mode: Selected preprocessing mode applied before analysis.

        Returns:
            The created AnalysisJob instance.

        Raises:
            Forbidden: If the job cannot be started due to insufficient cluster resources.
        """
        previous_jobs = cls.query.filter_by(experiment_id=experiment.id, simulation_path=simulation_path).all()
        for prev in previous_jobs:
            with suppress(Exception):  # job may already be cleaned up by K8s
                k8s.delete_job(f"analysis-{prev.id}")
            prev.cleanup_temp_files()
            db.session.delete(prev)
        db.session.flush()

        job_id = str(uuid.uuid4())[:12]
        job_name = f"analysis-{job_id}"

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
        if msg := k8s.check_quota_headroom(an_cpu, an_mem, an_cpu_limit, an_mem_limit):
            raise Forbidden(description=f"Cannot start analysis: {msg}")

        k8s.create_job(
            name=job_name,
            image=ANALYSIS_IMAGE,
            experiment_id=experiment.id,
            command=command,
            resources=ANALYSIS_RESOURCES,
        )

        job = AnalysisJob(
            id=job_id,  # type: ignore[call-arg]
            experiment_id=experiment.id,  # type: ignore[call-arg]
            simulation_path=simulation_path,  # type: ignore[call-arg]
            analysis_name=analysis_name,  # type: ignore[call-arg]
            structure_file=structure_file.as_posix() if structure_file else None,  # type: ignore[call-arg]
            trajectory_file=trajectory_file.as_posix(),  # type: ignore[call-arg]
            topology_file=topology_file.as_posix() if topology_file else None,  # type: ignore[call-arg]
        )
        db.session.add(job)
        db.session.commit()

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

    def delete(self) -> None:
        """Delete the K8s job and clean up any temporary files it left behind."""
        k8s.delete_job(self._job_name)
        self.cleanup_temp_files()
