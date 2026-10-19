"""Where mwf analyses read their input snapshots and write their result files."""

import json
from pathlib import Path
from typing import TYPE_CHECKING, Any

from core.config import DATA_DIR
from core.errors import NotFound, UnprocessableEntity

if TYPE_CHECKING:
    from modules.jobs.analysis.schemas import AnalysisVariant

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


def result_names(experiment_id: str, simulation_path: str) -> list[str]:
    """List the normalized names of the analysis results available for a simulation."""
    files = list_result_files(experiment_id, simulation_path)
    return [f.name[len(ANALYSIS_RESULT_PREFIX) : -len(ANALYSIS_RESULT_SUFFIX)].replace("_", "-") for f in files]


def read_variants(experiment_id: str, simulation_path: str, name: str) -> "list[AnalysisVariant]":
    """Variant options of a multi-file analysis from its summary JSON (empty when absent or not a summary)."""
    result_file = find_result_file(experiment_id, simulation_path, name)
    if not result_file:
        return []
    try:
        data = json.loads(result_file.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError):
        return []
    if isinstance(data, list) and all(
        isinstance(item, dict) and "analysis" in item and "name" in item for item in data
    ):
        return data
    return []


def read_result(experiment_id: str, simulation_path: str, name: str) -> Any:  # ruff:ignore[any-type]
    """
    JSON content of an analysis result file, as-is.

    Raises:
        NotFound: If the analysis result file does not exist.
        UnprocessableEntity: If the result file cannot be parsed as JSON.
    """
    result_file = find_result_file(experiment_id, simulation_path, name)
    if not result_file:
        raise NotFound(f"Analysis result '{name}' not found.")
    try:
        return json.loads(result_file.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError) as e:
        raise UnprocessableEntity("Failed to read analysis result.") from e
