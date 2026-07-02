import json
import logging
import os
from functools import lru_cache
from pathlib import Path

import jsonschema
from config import DATA_DIR
from enums import Engine
from extensions import db
from utils import FileInfo, get_files_with_extensions
from validators import check_path
from werkzeug.exceptions import BadRequest, NotFound

from .experiment import Experiment

logger = logging.getLogger(__name__)

SIMULATION_SUFFIX = ".simulation.json"
ENGINE_SCHEMA_FILE: dict[Engine, str] = {
    Engine.GMX: "gromacs.schema.json",
    Engine.AMBER: "amber.schema.json",
}
READONLY_MODE = 0o444
WRITABLE_MODE = 0o644


def _simulation_path(experiment_id: str, simulation_path: str) -> Path:
    check_path(simulation_path, DATA_DIR / experiment_id)
    return DATA_DIR / experiment_id / simulation_path


def list_simulation_files(experiment_id: str) -> list[FileInfo]:
    """
    Discover ``.simulation.json`` files under the experiment directory.

    Returns:
        Sorted list of FileInfo objects.
    """
    exp_dir = DATA_DIR / experiment_id
    if not exp_dir.is_dir():
        return []
    files = [f for f in get_files_with_extensions(exp_dir, "json") if f.name.endswith(SIMULATION_SUFFIX)]
    return sorted(files, key=lambda f: f.path)


def _resolve_schema_path(simulation_file: Path, raw: dict, exp_dir: Path) -> Path | None:
    schema_ref = raw.get("$schema")
    if not isinstance(schema_ref, str) or not schema_ref:
        return None
    resolved = (simulation_file.parent / schema_ref).resolve()
    try:
        resolved.relative_to(exp_dir.resolve())
    except ValueError:
        return None
    return resolved


@lru_cache(maxsize=16)
def _load_schema(schema_path: Path) -> dict | None:
    try:
        if not schema_path.is_file():
            return None
        return json.loads(schema_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def _resolved_files(experiment_id: str, simulation_path: str, files: dict) -> dict[str, str]:
    exp_dir = DATA_DIR / experiment_id
    sim_dir = (exp_dir / simulation_path).parent
    resolved: dict[str, str] = {}
    for role, rel in files.items():
        if not isinstance(rel, str) or not rel:
            continue
        try:
            absolute = (sim_dir / rel).resolve()
            absolute.relative_to(exp_dir.resolve())
            resolved[role] = str(absolute.relative_to(exp_dir.resolve()))
        except (OSError, ValueError):
            resolved[role] = rel
    return resolved


def _missing_files(experiment_id: str, resolved_files: dict[str, str]) -> list[str]:
    exp_dir = DATA_DIR / experiment_id
    return [role for role, rel in resolved_files.items() if not (exp_dir / rel).is_file()]


def _validate(
    experiment_id: str,
    simulation_path: str,
    raw: dict,
) -> tuple[bool, list[str], list[str], dict[str, str]]:
    """
    Validate a parsed manifest.

    Returns:
        Tuple of (valid, errors, missing_files, resolved_files).
    """
    errors: list[str] = []
    exp_dir = DATA_DIR / experiment_id
    simulation_file = exp_dir / simulation_path

    if not isinstance(raw, dict):
        return False, ["Manifest is not a JSON object."], [], {}

    files = raw.get("files")
    if not isinstance(files, dict):
        errors.append("Manifest is missing a 'files' object.")
        files = {}

    resolved_files = _resolved_files(experiment_id, simulation_path, files)

    schema_path = _resolve_schema_path(simulation_file, raw, exp_dir)
    schema = _load_schema(schema_path) if schema_path is not None else None
    if schema_path is None:
        errors.append("Missing or invalid '$schema' reference.")
    elif schema is None:
        errors.append(f"Schema file missing or unreadable: {raw.get('$schema')}")

    if schema is not None:
        try:
            jsonschema.validate(raw, schema)
        except jsonschema.ValidationError as exc:
            errors.append(f"Schema validation failed: {exc.message}")

    experiment = db.session.get(Experiment, experiment_id)
    if experiment is not None:
        sim_engine = raw.get("engine")
        if sim_engine != experiment.engine.value:
            errors.append(f"Engine '{sim_engine}' does not match experiment engine '{experiment.engine.value}'.")

    for role, rel in resolved_files.items():
        if rel and rel.startswith("/"):
            errors.append(f"File role '{role}' must be a relative path.")

    missing_files = _missing_files(experiment_id, resolved_files)

    valid = not errors
    return valid, errors, missing_files, resolved_files


def _to_response(
    experiment_id: str,
    simulation_path: str,
    raw: dict,
) -> dict:
    valid, errors, missing_files, resolved_files = _validate(experiment_id, simulation_path, raw)
    return {
        "simulation_path": simulation_path,
        "name": raw.get("name", ""),
        "engine": raw.get("engine", ""),
        "files": raw.get("files", {}) if isinstance(raw.get("files"), dict) else {},
        "resolved_files": resolved_files,
        "extra_args": raw.get("extra_args", ""),
        "locked": is_simulation_locked(experiment_id, simulation_path),
        "valid": valid,
        "errors": errors,
        "missing_files": missing_files,
    }


def list_simulations(experiment_id: str) -> list[dict]:
    """
    List all simulations with validation status, sorted by path.

    Returns:
        List of simulation response dicts.
    """
    simulations: list[dict] = []
    for file_info in list_simulation_files(experiment_id):
        simulation_file = DATA_DIR / experiment_id / file_info.path
        try:
            raw = json.loads(simulation_file.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            simulations.append({
                "simulation_path": file_info.path,
                "name": "",
                "engine": "",
                "files": {},
                "resolved_files": {},
                "extra_args": "",
                "locked": is_simulation_locked(experiment_id, file_info.path),
                "valid": False,
                "errors": [f"Failed to read simulation manifest: {exc}"],
                "missing_files": [],
            })
            continue
        simulations.append(_to_response(experiment_id, file_info.path, raw))
    return simulations


def get_simulation(experiment_id: str, simulation_path: str) -> dict:
    """
    Get a single simulation by path.

    Returns:
        Simulation response dict (includes invalid simulations).

    Raises:
        NotFound: If the file does not exist.
    """
    simulation_file = _simulation_path(experiment_id, simulation_path)
    if not simulation_file.is_file():
        raise NotFound(description=f"Simulation '{simulation_path}' not found.")
    try:
        raw = json.loads(simulation_file.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return {
            "simulation_path": simulation_path,
            "name": "",
            "engine": "",
            "files": {},
            "resolved_files": {},
            "extra_args": "",
            "locked": is_simulation_locked(experiment_id, simulation_path),
            "valid": False,
            "errors": [f"Failed to read simulation manifest: {exc}"],
            "missing_files": [],
        }
    return _to_response(experiment_id, simulation_path, raw)


def resolve_simulation_role(experiment_id: str, simulation: dict, role: str) -> Path:
    """
    Resolve a file role to an absolute Path.

    Returns:
        Absolute Path to the role file.

    Raises:
        BadRequest: If the role is absent or escapes the experiment directory.
    """
    files = simulation.get("files", {})
    rel = files.get(role)
    if not isinstance(rel, str) or not rel:
        raise BadRequest(description=f"Simulation is missing file role '{role}'.")
    simulation_file = _simulation_path(experiment_id, simulation["simulation_path"])
    resolved = (simulation_file.parent / rel).resolve()
    try:
        resolved.relative_to((DATA_DIR / experiment_id).resolve())
    except ValueError as exc:
        raise BadRequest(description=f"File role '{role}' escapes the experiment directory.") from exc
    return resolved


def simulation_files(experiment_id: str, simulation_path: str) -> dict[str, str]:
    """
    Return resolved file role paths for a simulation (no validation).

    Returns:
        Dict mapping file role to experiment-relative path.

    Raises:
        NotFound: If the manifest cannot be read.
    """
    simulation_file = _simulation_path(experiment_id, simulation_path)
    try:
        raw = json.loads(simulation_file.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise NotFound(description=f"Failed to read simulation '{simulation_path}': {exc}") from exc
    files = raw.get("files", {}) if isinstance(raw, dict) else {}
    return _resolved_files(experiment_id, simulation_path, files)


def validate_simulation_for_action(simulation: dict, action: str) -> None:
    """
    Validate a simulation may be used for an action.

    Raises:
        BadRequest: If the simulation is invalid or missing files.
    """
    if not simulation.get("valid"):
        errors = simulation.get("errors") or ["Simulation is invalid."]
        raise BadRequest(description=f"Cannot {action} invalid simulation: {'; '.join(errors)}")
    missing = simulation.get("missing_files") or []
    if missing:
        raise BadRequest(description=f"Cannot {action} simulation: missing files for roles: {', '.join(missing)}")


def is_simulation_job_locked(experiment_id: str, simulation_path: str) -> bool:
    """
    Return whether any tuner or production job references this simulation.

    Returns:
        True if a job references the simulation.
    """
    from .simulation_job import SimulationJob  # noqa: PLC0415
    from .tuner_job import TunerJob  # noqa: PLC0415

    return bool(
        TunerJob.query.filter_by(experiment_id=experiment_id, simulation_path=simulation_path).first()
        or SimulationJob.query.filter_by(experiment_id=experiment_id, simulation_path=simulation_path).first()
    )


def is_simulation_locked(experiment_id: str, simulation_path: str) -> bool:
    """
    Return whether a simulation is locked (read-only file or active job).

    Returns:
        True if locked.
    """
    simulation_file = _simulation_path(experiment_id, simulation_path)
    if simulation_file.exists() and not os.access(simulation_file, os.W_OK):
        return True
    return is_simulation_job_locked(experiment_id, simulation_path)


def mark_simulation_readonly(experiment_id: str, simulation_path: str) -> None:
    """Best-effort chmod a simulation manifest read-only (0444)."""
    simulation_file = _simulation_path(experiment_id, simulation_path)
    try:
        Path(simulation_file).chmod(READONLY_MODE)
    except OSError:
        logger.warning("Failed to mark simulation '%s' read-only", simulation_path, exc_info=True)


def _schema_for_engine(engine: Engine) -> str:
    try:
        return ENGINE_SCHEMA_FILE[engine]
    except KeyError as exc:
        raise BadRequest(description=f"Unsupported engine: {engine}") from exc


def _build_content(experiment_id: str, simulation_path: str, engine: Engine, payload: dict) -> dict:
    schema_filename = _schema_for_engine(engine)
    exp_dir = DATA_DIR / experiment_id
    sim_dir = (exp_dir / simulation_path).parent
    schema_ref = os.path.relpath(exp_dir / schema_filename, start=sim_dir)

    files = payload.get("files")
    if not isinstance(files, dict):
        raise BadRequest(description="'files' must be an object.")

    return {
        "$schema": schema_ref,
        "name": payload.get("name", ""),
        "engine": engine.value,
        "files": files,
        "extra_args": payload.get("extra_args", ""),
    }


def _validate_content_or_raise(experiment_id: str, simulation_path: str, content: dict, engine: Engine) -> None:
    exp_dir = DATA_DIR / experiment_id
    simulation_file = exp_dir / simulation_path
    schema_path = _resolve_schema_path(simulation_file, content, exp_dir)
    schema = _load_schema(schema_path) if schema_path is not None else None
    if schema is None:
        raise BadRequest(description=f"Schema file is missing or unreadable: {content.get('$schema')}")
    try:
        jsonschema.validate(content, schema)
    except jsonschema.ValidationError as exc:
        raise BadRequest(description=f"Simulation content is invalid: {exc.message}") from exc

    if content.get("engine") != engine.value:
        raise BadRequest(description="Simulation engine does not match the experiment engine.")


def _safe_default_path(name: str) -> str:
    safe_name = Path(name).name if name else "simulation"
    return f"production/{safe_name}{SIMULATION_SUFFIX}"


def write_simulation(experiment_id: str, payload: dict) -> dict:
    """
    Create a simulation manifest at ``production/{name}.simulation.json``.

    Returns:
        The created simulation response dict.

    Raises:
        BadRequest: If the path is unsafe, locked, or content is invalid.
    """
    experiment = Experiment.query.get_or_404(experiment_id, description=f"Experiment {experiment_id} not found")
    simulation_path = payload.get("simulation_path") or _safe_default_path(payload.get("name", ""))
    simulation_path = Path(simulation_path).as_posix()
    check_path(simulation_path, DATA_DIR / experiment_id)
    if not simulation_path.endswith(SIMULATION_SUFFIX):
        raise BadRequest(description=f"Path must end with '{SIMULATION_SUFFIX}'.")

    simulation_file = _simulation_path(experiment_id, simulation_path)
    if simulation_file.exists() and is_simulation_job_locked(experiment_id, simulation_path):
        raise BadRequest(description=f"Simulation '{simulation_path}' is locked.")

    content = _build_content(experiment_id, simulation_path, experiment.engine, payload)
    _validate_content_or_raise(experiment_id, simulation_path, content, experiment.engine)

    simulation_file.parent.mkdir(parents=True, exist_ok=True)
    simulation_file.write_text(json.dumps(content, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return _to_response(experiment_id, simulation_path, content)


def update_simulation(experiment_id: str, simulation_path: str, payload: dict) -> dict:
    """
    Edit an unlocked simulation manifest.

    Returns:
        The updated simulation response dict.

    Raises:
        NotFound: If the file does not exist.
        BadRequest: If job-locked or content is invalid.
    """
    experiment = Experiment.query.get_or_404(experiment_id, description=f"Experiment {experiment_id} not found")
    simulation_path = Path(simulation_path).as_posix()
    simulation_file = _simulation_path(experiment_id, simulation_path)
    if not simulation_file.is_file():
        raise NotFound(description=f"Simulation '{simulation_path}' not found.")

    if is_simulation_job_locked(experiment_id, simulation_path):
        raise BadRequest(description=f"Simulation '{simulation_path}' is locked.")

    content = _build_content(experiment_id, simulation_path, experiment.engine, payload)
    _validate_content_or_raise(experiment_id, simulation_path, content, experiment.engine)

    if simulation_file.exists() and not os.access(simulation_file, os.W_OK):
        try:
            Path(simulation_file).chmod(WRITABLE_MODE)
        except OSError:
            logger.warning("Failed to make simulation '%s' writable", simulation_path, exc_info=True)

    simulation_file.write_text(json.dumps(content, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    try:
        Path(simulation_file).chmod(WRITABLE_MODE)
    except OSError:
        logger.warning("Failed to restore writable mode for '%s'", simulation_path, exc_info=True)

    return _to_response(experiment_id, simulation_path, content)
