import io
import shutil
import zipfile
from functools import lru_cache
from pathlib import Path

from config import DATA_DIR

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
    """Ensure AMBER demo files exist for an experiment.

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


def write_running_gmx_log(experiment_id: str, deffnm: str, initial_lines: int = 120) -> int:
    return write_gmx_log_from_template(experiment_id, deffnm, initial_lines=initial_lines)


def write_finished_gmx_log(
    experiment_id: str,
    deffnm: str,
    nsteps: int,  # noqa: ARG001
    performance: float,  # noqa: ARG001
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
    log_path.write_text("\n".join(template_lines[:line_count]), encoding="utf-8")
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

    lines_to_append = template_lines[current_line_count:capped_index]
    with log_path.open("a", encoding="utf-8") as log_file:
        if current_line_count > 0 and lines_to_append:
            log_file.write("\n")
        log_file.write("\n".join(lines_to_append))

    return capped_index


def append_remaining_gmx_log_template(experiment_id: str, deffnm: str) -> None:
    append_gmx_log_template_until(experiment_id, deffnm, gmx_log_template_line_count())


def gmx_log_template_line_count() -> int:
    return len(_gmx_log_template_lines())


def _gmx_log_template_lines() -> list[str]:
    return list(_gmx_log_template_tuple())


@lru_cache(maxsize=1)
def _gmx_log_template_tuple() -> tuple[str, ...]:
    return tuple(_read_fixture(DEFAULT_GMX_LOG_FILE).decode("utf-8").splitlines())


def _read_fixture(path: Path) -> bytes:
    if not path.exists():
        raise FileNotFoundError(f"Missing demo fixture: {path}")
    return path.read_bytes()
