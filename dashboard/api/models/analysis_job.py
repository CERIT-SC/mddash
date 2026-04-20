import logging
import shlex
import shutil
import uuid
from contextlib import suppress
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING

from cache import analysis_status_cache
from cachetools import cached
from clients import k8s
from clients.k8s import parse_cpu, parse_memory
from config import ANALYSIS_IMAGE, ANALYSIS_RESOURCES, DATA_DIR
from enums import AnalysisType, JobStatus, PreprocessingMode
from extensions import db, enum_values
from sqlalchemy.orm import Mapped, mapped_column, relationship
from werkzeug.exceptions import Forbidden

if TYPE_CHECKING:
    from .experiment import Experiment


logger = logging.getLogger(__name__)

ANALYSIS_RESULT_PREFIX = "mda."
ANALYSIS_RESULT_SUFFIX = ".json"
MWF_DIR = "mwf_analyses"
MWF_INPUTS_DIR = "mwf_inputs"
MWF_INCOMPLETE_PREFIX = "incomplete_"
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
    return [Path(incomplete_dir), Path(MWF_DIR) / incomplete_dir]


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


def find_result_file(experiment_id: str, name: str) -> Path | None:
    """
    Find a result file by normalized name under the mwf output directory.

    Returns:
        The first matching Path, or None if not found.
    """
    filename = f"{ANALYSIS_RESULT_PREFIX}{name.replace('-', '_')}{ANALYSIS_RESULT_SUFFIX}"
    mwf_dir = DATA_DIR / experiment_id / MWF_DIR
    if not mwf_dir.is_dir():
        return None
    matches = list(mwf_dir.rglob(filename))
    return matches[0] if matches else None


def list_result_files(experiment_id: str) -> list[Path]:
    """
    List all mda.*.json result files under the mwf output directory.

    Returns:
        Sorted list of matching Paths, or empty list if directory doesn't exist.
    """
    mwf_dir = DATA_DIR / experiment_id / MWF_DIR
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
    lines = ["name: mddash", "type: trajectory"]
    if analysis_name in AUTO_INTERACTION_ANALYSES:
        lines.extend(["interactions:", "  - auto"])
    return "\n".join(lines) + "\n"


def _safe_copy(src: Path, dst: Path) -> str:
    src_q = shlex.quote(src.as_posix())
    dst_q = shlex.quote(dst.as_posix())
    return f"[ {src_q} -ef {dst_q} ] || cp {src_q} {dst_q}"


def format_mwf_analysis_command(
    analysis_name: AnalysisType,
    structure_file: Path,
    trajectory_file: Path,
    topology_file: Path | None,
    preprocessing_mode: PreprocessingMode,
) -> str:
    """
    Build the mwf command for a single analysis job.

    Returns:
        Shell command string used to execute the requested mwf analysis.
    """
    structure_snapshot = Path(MWF_INPUTS_DIR) / f"input_structure{structure_file.suffix}"
    trajectory_snapshot = Path(MWF_INPUTS_DIR) / f"input_trajectory{trajectory_file.suffix}"
    topology_snapshot = Path(MWF_INPUTS_DIR) / f"input_topology{topology_file.suffix}" if topology_file else None

    snapshot_commands = [
        _safe_copy(structure_file, structure_snapshot),
        _safe_copy(trajectory_file, trajectory_snapshot),
    ]
    if topology_file and topology_snapshot:
        snapshot_commands.append(_safe_copy(topology_file, topology_snapshot))

    flags = [f"-top {shlex.quote(topology_snapshot.as_posix())}" if topology_snapshot else "-top no"]
    if preprocessing_mode in {PreprocessingMode.IMAGE, PreprocessingMode.IMAGE_FIT}:
        flags.append("-img")
    if preprocessing_mode is PreprocessingMode.IMAGE_FIT:
        flags.append("-fit")

    inputs_yaml = shlex.quote(format_mwf_inputs_yaml(analysis_name))
    prelude_commands = get_runtime_prelude_commands(analysis_name)

    commands = [
        f"mkdir -p {shlex.quote(MWF_INPUTS_DIR)} {shlex.quote(MWF_DIR)}",
        *prelude_commands,
        *snapshot_commands,
        f"printf %s {inputs_yaml} > inputs.yaml",
        "conda run --no-capture-output -n mwf_env "
        f"mwf run -dir . -stru {shlex.quote(structure_snapshot.as_posix())} "
        f"-md {shlex.quote(MWF_DIR)} {shlex.quote(trajectory_snapshot.as_posix())} "
        f"{' '.join(flags)} -i {analysis_name}",
    ]
    return " && ".join(commands)


class AnalysisJob(db.Model):  # type: ignore
    """On-demand MD analysis job running mddb-workflow in a K8s Job."""

    __tablename__ = "analysis_jobs"

    id: Mapped[str] = mapped_column(db.String(36), primary_key=True)
    experiment_id: Mapped[str] = mapped_column(db.String(5), db.ForeignKey("experiments.id"))
    created_at: Mapped[datetime] = mapped_column(db.DateTime, default=datetime.now)

    analysis_name: Mapped[AnalysisType] = mapped_column(
        db.Enum(AnalysisType, values_callable=enum_values), nullable=False
    )
    structure_file: Mapped[str] = mapped_column(db.String(255), nullable=False)
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
        if self._last_known_status is not None and self._last_known_status in {JobStatus.TERMINATED, JobStatus.ERROR}:
            return self._last_known_status

        try:
            fetched = k8s.get_job_status(self._job_name)
            if fetched not in {self._last_known_status, JobStatus.UNKNOWN}:
                self._last_known_status = fetched
                db.session.commit()
                if fetched == JobStatus.TERMINATED:
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
        analysis_name: AnalysisType,
        structure_file: Path,
        trajectory_file: Path,
        topology_file: Path | None,
        preprocessing_mode: PreprocessingMode,
    ) -> "AnalysisJob":
        """
        Start an analysis K8s Job for a single analysis type.

        Args:
            experiment: The experiment to run analysis on.
            analysis_name: The mwf analysis task name (e.g. "rmsds", "pca").
            structure_file: Relative path to the structure file within the experiment dir.
            trajectory_file: Relative path to the trajectory file within the experiment dir.
            topology_file: Relative path to the topology file, when required for preprocessing or analysis.
            preprocessing_mode: Selected preprocessing mode applied before analysis.

        Returns:
            The created AnalysisJob instance.

        Raises:
            Forbidden: If the job cannot be started due to insufficient cluster resources.
        """
        previous_jobs = cls.query.filter_by(experiment_id=experiment.id).all()
        for prev in previous_jobs:
            with suppress(Exception):  # job may already be cleaned up by K8s
                k8s.delete_job(f"analysis-{prev.id}")
            prev.cleanup_temp_files()
            db.session.delete(prev)
        db.session.flush()

        job_id = str(uuid.uuid4())[:12]
        job_name = f"analysis-{job_id}"

        # conda run needed because create_job uses sh -c which bypasses the ENTRYPOINT.
        # mwf_analyses/ is the MD dir; mwf forbids MD dir == project dir.
        # No -k flag: with a single analysis there's nothing to "keep going" to,
        # and it masks errors (mwf exits 0 even on InputError).
        command = format_mwf_analysis_command(
            analysis_name=analysis_name,
            structure_file=structure_file,
            trajectory_file=trajectory_file,
            topology_file=topology_file,
            preprocessing_mode=preprocessing_mode,
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
            analysis_name=analysis_name,  # type: ignore[call-arg]
            structure_file=structure_file.as_posix(),  # type: ignore[call-arg]
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

        mwf_dir = exp_dir / MWF_DIR
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
