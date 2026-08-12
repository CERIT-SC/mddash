import io
import json
import re
import shutil
import zipfile
from datetime import datetime
from functools import lru_cache
from pathlib import Path

from config import DATA_DIR
from enums import Engine
from manifest_schema import schema_url

DEMO_DATA_DIR = Path(__file__).resolve().parent / "data"
DEFAULT_TPR_FILE = DEMO_DATA_DIR / "md.tpr"
DEFAULT_XTC_FILE = DEMO_DATA_DIR / "trajectory.xtc"
DEFAULT_PDB_FILE = DEMO_DATA_DIR / "structure.pdb"
DEFAULT_GMX_LOG_FILE = DEMO_DATA_DIR / "md.log"
DEFAULT_PARM7_FILE = DEMO_DATA_DIR / "md.parm7"
DEFAULT_INPCRD_FILE = DEMO_DATA_DIR / "md.inpcrd"
DEFAULT_MDIN_FILE = DEMO_DATA_DIR / "md.mdin"
DEFAULT_NC_FILE = DEMO_DATA_DIR / "trajectory.nc"
DEFAULT_AMBER_PDB_FILE = DEMO_DATA_DIR / "amber_structure.pdb"
DEFAULT_AMBER_OUT_FILE = DEMO_DATA_DIR / "md.out"
DEFAULT_AMBER_MDINFO_FILE = DEMO_DATA_DIR / "md.mdinfo"
DEFAULT_GRO_FILE = DEMO_DATA_DIR / "reference.gro"
MDPOSIT_DEMO_ACCESSION = "MD-DEMO01.1"
MDPOSIT_DEMO_PROJECT_URL = f"https://mdposit.mddbr.eu/projects/{MDPOSIT_DEMO_ACCESSION}"
MDPOSIT_DEMO_FILES = {
    "mdposit/structure.pdb": DEFAULT_PDB_FILE,
    "mdposit/topology.tpr": DEFAULT_TPR_FILE,
    "mdposit/trajectory.xtc": DEFAULT_XTC_FILE,
}


def write_gmx_simulation(
    experiment_id: str,
    name: str,
    simulation_path: str = "",
    topology: str | None = None,
    structure: str | None = None,
    trajectory: str | None = None,
    extra_args: str = "",
) -> str:
    experiment_dir = DATA_DIR / experiment_id
    sim_path = simulation_path or f"{name}.simulation.json"
    sim_file = experiment_dir / sim_path
    sim_file.parent.mkdir(parents=True, exist_ok=True)
    content = {
        "$schema": schema_url(Engine.GMX),
        "name": name,
        "engine": "GMX",
        "files": {
            "run_input": topology or f"production/{name}.tpr",
            "reference_structure": structure or f"analysis/{name}-reference.gro",
            "trajectory": trajectory or f"production/{name}.xtc",
        },
        "extra_args": extra_args,
    }
    _write_manifest(sim_file, content)
    # Materialize viewer files so the Trajectory Viewer works for seeded simulations.
    _copy_if_missing(experiment_dir / content["files"]["reference_structure"], DEFAULT_GRO_FILE)
    _copy_if_missing(experiment_dir / content["files"]["trajectory"], DEFAULT_XTC_FILE)
    return sim_path


def write_amber_simulation(
    experiment_id: str,
    name: str,
    simulation_path: str = "",
    topology: str | None = None,
    coordinates: str | None = None,
    control: str | None = None,
    trajectory: str | None = None,
    extra_args: str = "",
) -> str:
    experiment_dir = DATA_DIR / experiment_id
    sim_path = simulation_path or f"{name}.simulation.json"
    sim_file = experiment_dir / sim_path
    sim_file.parent.mkdir(parents=True, exist_ok=True)
    content = {
        "$schema": schema_url(Engine.AMBER),
        "name": name,
        "engine": "AMBER",
        "files": {
            "topology": topology or f"{name}.prmtop",
            "coordinates": coordinates or f"{name}.rst7",
            "control": control or f"{name}.mdin",
            "reference_structure": f"analysis/{name}-reference.pdb",
            "trajectory": trajectory or f"{name}.nc",
        },
        "extra_args": extra_args,
    }
    _write_manifest(sim_file, content)
    # Materialize viewer files so the Trajectory Viewer works for seeded simulations.
    _copy_if_missing(experiment_dir / content["files"]["reference_structure"], DEFAULT_AMBER_PDB_FILE)
    _copy_if_missing(experiment_dir / content["files"]["trajectory"], DEFAULT_NC_FILE)
    return sim_path


def _write_manifest(sim_file: Path, content: dict) -> None:
    if sim_file.exists():
        # A previous demo run may have locked the manifest read-only (0444).
        sim_file.chmod(0o644)
    sim_file.write_text(json.dumps(content, indent=2, sort_keys=True), encoding="utf-8")


FIXTURE_BY_SUFFIX = {
    ".tpr": DEFAULT_TPR_FILE,
    ".xtc": DEFAULT_XTC_FILE,
    ".pdb": DEFAULT_PDB_FILE,
    ".prmtop": DEFAULT_PARM7_FILE,
    ".parm7": DEFAULT_PARM7_FILE,
    ".inpcrd": DEFAULT_INPCRD_FILE,
    ".mdin": DEFAULT_MDIN_FILE,
    ".nc": DEFAULT_NC_FILE,
}


def ensure_demo_files(experiment_id: str, filenames: list[str]) -> None:
    experiment_dir = DATA_DIR / experiment_id
    experiment_dir.mkdir(parents=True, exist_ok=True)
    for filename in filenames:
        file_path = experiment_dir / filename
        if file_path.exists():
            continue
        file_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(_resolve_fixture_path(filename), file_path)


def build_demo_archive_bytes() -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as zf:
        zf.writestr("input.tpr", _read_fixture(DEFAULT_TPR_FILE))
        zf.writestr("trajectory.xtc", _read_fixture(DEFAULT_XTC_FILE))
        zf.writestr("input.pdb", _read_fixture(DEFAULT_PDB_FILE))
    return buffer.getvalue()


def ensure_amber_demo_files(
    experiment_id: str,
    prmtop_name: str,
    inpcrd_name: str,
    mdin_names: list[str],
) -> None:
    """
    Ensure AMBER demo files exist for an experiment.

    Creates AMBER topology, coordinate, input, structure, trajectory, and parm7
    files using default fixture files if they don't already exist.

    Args:
        experiment_id: The experiment ID.
        prmtop_name: Name of the PRMTOP file.
        inpcrd_name: Name of the INPCRD file.
        mdin_names: List of MDIN file names to create.
    """
    experiment_dir = DATA_DIR / experiment_id
    experiment_dir.mkdir(parents=True, exist_ok=True)

    # Copy prmtop file
    prmtop_path = experiment_dir / prmtop_name
    if not prmtop_path.exists():
        prmtop_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(_resolve_fixture_path(prmtop_name), prmtop_path)

    # Copy inpcrd file
    inpcrd_path = experiment_dir / inpcrd_name
    if not inpcrd_path.exists():
        inpcrd_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(_resolve_fixture_path(inpcrd_name), inpcrd_path)

    # Copy each mdin file
    for mdin_name in mdin_names:
        mdin_path = experiment_dir / mdin_name
        if not mdin_path.exists():
            mdin_path.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(_resolve_fixture_path(mdin_name), mdin_path)

    # Analysis files: matching structure PDB + NetCDF trajectory + parm7 topology
    _copy_if_missing(experiment_dir / "structure.pdb", DEFAULT_AMBER_PDB_FILE)
    _copy_if_missing(experiment_dir / "trajectory.nc", DEFAULT_NC_FILE)
    _copy_if_missing(experiment_dir / f"{Path(prmtop_name).stem}.parm7", DEFAULT_PARM7_FILE)


def ensure_mdposit_demo_files(experiment_id: str) -> None:
    experiment_dir = DATA_DIR / experiment_id
    experiment_dir.mkdir(parents=True, exist_ok=True)
    for filename, fixture_path in MDPOSIT_DEMO_FILES.items():
        _copy_if_missing(experiment_dir / filename, fixture_path)


def get_mdposit_fixture_bytes(filename: str) -> bytes | None:
    fixture_path = MDPOSIT_DEMO_FILES.get(filename)
    if fixture_path is None:
        return None
    return _read_fixture(fixture_path)


def _copy_if_missing(dest: Path, src: Path) -> None:
    if not dest.exists() and src.exists():
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dest)


def _resolve_fixture_path(filename: str) -> Path:
    direct_match = DEMO_DATA_DIR / filename
    if direct_match.exists():
        return direct_match

    fixture = FIXTURE_BY_SUFFIX.get(Path(filename).suffix.lower())
    if fixture is not None and fixture.exists():
        return fixture

    raise FileNotFoundError(f"Missing demo fixture for '{filename}' in {DEMO_DATA_DIR}")


def write_running_gmx_log(experiment_id: str, deffnm: str, initial_lines: int | None = None) -> int:
    if initial_lines is None:
        # Start right after "Started mdrun" (+ first step row) so the progress parser finds steps.
        initial_lines = min(gmx_log_start_index() + 3, gmx_log_template_line_count())
    return write_gmx_log_from_template(experiment_id, deffnm, initial_lines=initial_lines)


def gmx_log_start_index() -> int:
    return (
        next(
            (i for i, line in enumerate(_gmx_log_template_tuple()) if "Started mdrun" in line),
            0,
        )
        + 1
    )


def gmx_log_steps_end_index() -> int:
    """Line index past the last "step time" row; the rest is the perf summary + Finished."""
    for i in range(len(_gmx_log_template_tuple()) - 1, -1, -1):
        if re.match(r"\s*\d+\s+\d+\.\d+\s*$", _gmx_log_template_tuple()[i]):
            return i + 1
    return gmx_log_template_line_count()


def write_finished_gmx_log(
    experiment_id: str,
    deffnm: str,
    nsteps: int,  # ruff:ignore[unused-function-argument]
    performance: float,  # ruff:ignore[unused-function-argument]
    append_only: bool = False,
) -> None:
    if append_only:
        append_remaining_gmx_log_template(experiment_id, deffnm)
        return
    write_gmx_log_from_template(experiment_id, deffnm, initial_lines=gmx_log_template_line_count())


def write_gmx_log_from_template(experiment_id: str, deffnm: str, initial_lines: int = 120) -> int:
    template_lines = _gmx_log_template_lines()
    line_count = min(initial_lines, len(template_lines))
    log_path = DATA_DIR / experiment_id / f"{deffnm}.log"
    log_path.parent.mkdir(parents=True, exist_ok=True)
    log_path.write_text("\n".join(_stamp_mdrun_dates(template_lines[:line_count])), encoding="utf-8")
    return line_count


def append_gmx_log_template_until(experiment_id: str, deffnm: str, next_line_index: int) -> int:
    template_lines = _gmx_log_template_lines()
    capped_index = min(max(0, next_line_index), len(template_lines))
    log_path = DATA_DIR / experiment_id / f"{deffnm}.log"

    current_line_count = 0
    if log_path.exists():
        current_line_count = len(log_path.read_text(encoding="utf-8").splitlines())

    if capped_index <= current_line_count:
        return current_line_count

    lines_to_append = _stamp_mdrun_dates(template_lines[current_line_count:capped_index])
    with log_path.open("a", encoding="utf-8") as log_file:
        if current_line_count > 0 and lines_to_append:
            log_file.write("\n")
        log_file.write("\n".join(lines_to_append))

    return capped_index


def _stamp_mdrun_dates(lines: list[str]) -> list[str]:
    """Replace the template's hardcoded 2025 mdrun dates with the current time."""
    now = datetime.now().strftime("%a %b %d %H:%M:%S %Y")
    return [re.sub(r"(Started|Finished) mdrun on rank 0 \S.*$", rf"\1 mdrun on rank 0 {now}", line) for line in lines]


def append_remaining_gmx_log_template(experiment_id: str, deffnm: str) -> None:
    append_gmx_log_template_until(experiment_id, deffnm, gmx_log_template_line_count())


def gmx_log_template_line_count() -> int:
    return len(_gmx_log_template_lines())


def _gmx_log_template_lines() -> list[str]:
    return list(_gmx_log_template_tuple())


def write_running_amber_log(experiment_id: str, deffnm: str) -> None:
    """Write a partial mdout (no final performance block) and a live mdinfo."""
    lines = _amber_out_template_lines()
    cut = next((i for i, line in enumerate(lines) if "Final Performance Info" in line), len(lines))
    out_path = DATA_DIR / experiment_id / f"{deffnm}.out"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text("\n".join(lines[:cut]), encoding="utf-8")

    mdinfo_path = DATA_DIR / experiment_id / f"{deffnm}.mdinfo"
    mdinfo_path.parent.mkdir(parents=True, exist_ok=True)
    mdinfo_path.write_text(_read_fixture(DEFAULT_AMBER_MDINFO_FILE).decode("utf-8"), encoding="utf-8")


def write_finished_amber_log(experiment_id: str, deffnm: str) -> None:
    out_path = DATA_DIR / experiment_id / f"{deffnm}.out"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(DEFAULT_AMBER_OUT_FILE, out_path)


def write_mdrun_stdio(experiment_id: str, sim_dir: str, job_id: str) -> None:
    """Write the mdrun-<id> stdout/stderr files a running job produces."""
    run_dir = DATA_DIR / experiment_id / sim_dir
    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / f"mdrun-{job_id}.out").write_text(f"Demo mdrun job {job_id} started.\n", encoding="utf-8")
    (run_dir / f"mdrun-{job_id}.err").touch()


def write_amber_mdinfo(experiment_id: str, deffnm: str, nstep: int) -> None:
    """Write a one-line mdinfo, as pmemd rewrites it in place during a run."""
    mdinfo_path = DATA_DIR / experiment_id / f"{deffnm}.mdinfo"
    mdinfo_path.parent.mkdir(parents=True, exist_ok=True)
    mdinfo_path.write_text(
        f" NSTEP = {nstep:>8}   TIME(PS) = {nstep * 0.002:>10.3f}  TEMP(K) =   300.01  PRESS =     0.0\n",
        encoding="utf-8",
    )


@lru_cache(maxsize=1)
def _amber_out_template_lines() -> tuple[str, ...]:
    return tuple(_read_fixture(DEFAULT_AMBER_OUT_FILE).decode("utf-8").splitlines())


@lru_cache(maxsize=1)
def _gmx_log_template_tuple() -> tuple[str, ...]:
    return tuple(_read_fixture(DEFAULT_GMX_LOG_FILE).decode("utf-8").splitlines())


def _read_fixture(path: Path) -> bytes:
    if not path.exists():
        raise FileNotFoundError(f"Missing demo fixture: {path}")
    return path.read_bytes()
