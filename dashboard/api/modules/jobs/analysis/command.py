"""The shell command an analysis K8s Job runs: input snapshots, mwf quirks prep, and the mwf invocation."""

import shlex
from pathlib import Path

from core.enums import AnalysisType, Engine, PreprocessingMode

from modules.jobs.analysis.results import MWF_INCOMPLETE_PREFIX, MWF_INPUTS_DIR, mwf_output_dir

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
    """Directory mwf leaves for an incomplete `task_name` run, relative to the experiment dir (a list for the cleanup loop)."""
    incomplete_dir = f"{MWF_INCOMPLETE_PREFIX}{task_name}"
    return [Path(incomplete_dir)]


def get_analysis_runtime_prep_commands(analysis_name: AnalysisType) -> list[str]:
    """Build analysis-specific shell prep for known third-party mwf quirks."""
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


def get_runtime_prelude_commands(analysis_name: AnalysisType) -> list[str]:
    """Build shell commands that prepare the third-party mwf container runtime."""
    commands = [
        'export HOME="$PWD/.mddash-home"',
        'mkdir -p "$HOME"',
        "git config --global --add safe.directory /app/MDDB-workflow >/dev/null 2>&1 || true",
    ]
    commands.extend(get_analysis_runtime_prep_commands(analysis_name))
    return commands


def format_mwf_inputs_yaml(analysis_name: AnalysisType) -> str:
    """Build the minimal inputs.yaml content for an analysis job."""
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
