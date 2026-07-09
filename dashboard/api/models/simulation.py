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


@lru_cache(maxsize=16)
def _load_schema(schema_path: Path) -> dict | None:
    try:
        if not schema_path.is_file():
            return None
        return json.loads(schema_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def _safe_default_path(name: str) -> str:
    safe_name = Path(name).name if name else "simulation"
    return f"{safe_name}{SIMULATION_SUFFIX}"


def _build_content(experiment_id: str, simulation_path: str, engine: Engine, payload: dict) -> dict:
    schema_filename = ENGINE_SCHEMA_FILE[engine]
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
    schema_ref = content.get("$schema")
    if not isinstance(schema_ref, str) or not schema_ref:
        raise BadRequest(description="Missing or invalid '$schema' reference.")
    schema_path = (simulation_file.parent / schema_ref).resolve()
    try:
        schema_path.relative_to(exp_dir.resolve())
    except ValueError:
        raise BadRequest(description=f"Schema file escapes experiment directory: {schema_ref}")
    schema = _load_schema(schema_path)
    if schema is None:
        raise BadRequest(description=f"Schema file is missing or unreadable: {schema_ref}")
    try:
        jsonschema.validate(content, schema)
    except jsonschema.ValidationError as exc:
        raise BadRequest(description=f"Simulation content is invalid: {exc.message}") from exc

    if content.get("engine") != engine.value:
        raise BadRequest(description="Simulation engine does not match the experiment engine.")


class Simulation:  # noqa: PLR0904
    """File-backed simulation manifest (`.simulation.json`)."""

    def __init__(
        self,
        experiment_id: str,
        simulation_path: str,
        raw: dict | None = None,
        read_error: str | None = None,
    ) -> None:
        """Initialize a Simulation instance from raw manifest data or a read error."""
        self.experiment_id = experiment_id
        self.simulation_path = simulation_path
        self._raw = raw if isinstance(raw, dict) else {}
        self._read_error = read_error
        self._resolved: dict[str, str] | None = None
        self._validation: tuple[bool, list[str], list[str]] | None = None

    @property
    def _file(self) -> Path:
        """Absolute path to the manifest file."""
        return DATA_DIR / self.experiment_id / self.simulation_path

    @property
    def name(self) -> str:
        """Simulation name from the manifest."""
        return self._raw.get("name", "")

    @property
    def engine(self) -> str:
        """Engine value from the manifest."""
        return self._raw.get("engine", "")

    @property
    def extra_args(self) -> str:
        """Extra CLI arguments from the manifest."""
        return self._raw.get("extra_args", "")

    @property
    def files(self) -> dict[str, str]:
        """Raw file role paths from the manifest."""
        f = self._raw.get("files")
        return f if isinstance(f, dict) else {}

    @property
    def resolved_files(self) -> dict[str, str]:
        """Experiment-relative paths for each file role."""
        if self._resolved is None:
            self._resolved = self._resolve_files(self.files)
        return self._resolved

    @property
    def valid(self) -> bool:
        """Whether the manifest passes validation."""
        return self._run_validation()[0]

    @property
    def errors(self) -> list[str]:
        """Validation errors, if any."""
        return self._run_validation()[1]

    @property
    def missing_files(self) -> list[str]:
        """File roles whose resolved path does not exist."""
        return self._run_validation()[2]

    @property
    def locked(self) -> bool:
        """Whether the simulation is locked (read-only file or active job references)."""
        return self.is_locked(self.experiment_id, self.simulation_path)

    def to_dict(self) -> dict:
        """
        Serialize to the API response dict.

        Returns:
            Dict with simulation_path, name, engine, files, resolved_files,
            extra_args, locked, valid, errors, missing_files.
        """
        valid, errors, missing = self._run_validation()
        return {
            "simulation_path": self.simulation_path,
            "name": self.name,
            "engine": self.engine,
            "files": self.files,
            "resolved_files": self.resolved_files,
            "extra_args": self.extra_args,
            "locked": self.locked,
            "valid": valid,
            "errors": errors,
            "missing_files": missing,
        }

    def resolve_role(self, role: str) -> Path:
        """
        Resolve a file role to an absolute Path.

        Roles are resolved relative to the experiment directory, consistent with
        ``resolved_files`` and the manifest writer convention.

        Returns:
            Absolute Path to the role file.

        Raises:
            BadRequest: If the role is absent or escapes the experiment directory.
        """
        rel = self.files.get(role)
        if not isinstance(rel, str) or not rel:
            raise BadRequest(description=f"Simulation is missing file role '{role}'.")
        exp_dir = (DATA_DIR / self.experiment_id).resolve()
        resolved = (exp_dir / rel).resolve()
        try:
            resolved.relative_to(exp_dir)
        except ValueError as exc:
            raise BadRequest(description=f"File role '{role}' escapes the experiment directory.") from exc
        return resolved

    def require_files(self, roles: list[str] | None = None) -> None:
        """
        Require simulation file roles to exist.

        Raises:
            BadRequest: If invalid or missing files.
        """
        if not self.valid:
            errors = self.errors or ["Simulation is invalid."]
            raise BadRequest(description=f"Invalid simulation: {'; '.join(errors)}")
        missing_files = self.missing_files
        if roles is not None:
            missing_files = [role for role in roles if role in self.missing_files or not self.files.get(role)]
        if missing_files:
            raise BadRequest(description=f"Missing files for roles: {', '.join(missing_files)}")

    def mark_readonly(self) -> None:
        """Best-effort chmod the manifest read-only (0444)."""
        try:
            self._file.chmod(READONLY_MODE)
        except OSError:
            logger.warning("Failed to mark simulation '%s' read-only", self.simulation_path, exc_info=True)

    def _resolve_files(self, files: dict) -> dict[str, str]:
        """
        Resolve file roles to experiment-relative paths.

        Returns:
            Dict mapping role to experiment-relative path.
        """
        exp_dir = (DATA_DIR / self.experiment_id).resolve()
        resolved: dict[str, str] = {}
        for role, rel in files.items():
            if not isinstance(rel, str) or not rel:
                continue
            try:
                absolute = (exp_dir / rel).resolve()
                absolute.relative_to(exp_dir)
                resolved[role] = str(absolute.relative_to(exp_dir))
            except (OSError, ValueError):
                resolved[role] = rel
        return resolved

    def _run_validation(self) -> tuple[bool, list[str], list[str]]:
        """
        Run validation if not cached.

        Returns:
            Tuple of (valid, errors, missing_files).
        """
        if self._validation is not None:
            return self._validation

        if self._read_error:
            self._validation = False, [f"Failed to read simulation manifest: {self._read_error}"], []
            return self._validation

        errors: list[str] = []
        resolved = self.resolved_files
        exp_dir = DATA_DIR / self.experiment_id

        schema_path = self._resolve_schema_path(exp_dir)
        schema = _load_schema(schema_path) if schema_path is not None else None
        if schema_path is None:
            errors.append("Missing or invalid '$schema' reference.")
        elif schema is None:
            errors.append(f"Schema file missing or unreadable: {self._raw.get('$schema')}")

        if schema is not None:
            try:
                jsonschema.validate(self._raw, schema)
            except jsonschema.ValidationError as exc:
                errors.append(f"Schema validation failed: {exc.message}")

        experiment = db.session.get(Experiment, self.experiment_id)
        if experiment is not None:
            sim_engine = self._raw.get("engine")
            if sim_engine != experiment.engine.value:
                errors.append(f"Engine '{sim_engine}' does not match experiment engine '{experiment.engine.value}'.")

        for role, rel in resolved.items():
            if rel and rel.startswith("/"):
                errors.append(f"File role '{role}' must be a relative path.")

        missing = [role for role, rel in resolved.items() if not (exp_dir / rel).is_file()]

        self._validation = not errors, errors, missing
        return self._validation

    def _resolve_schema_path(self, exp_dir: Path) -> Path | None:
        schema_ref = self._raw.get("$schema")
        if not isinstance(schema_ref, str) or not schema_ref:
            return None
        resolved = (self._file.parent / schema_ref).resolve()
        try:
            resolved.relative_to(exp_dir.resolve())
        except ValueError:
            return None
        return resolved

    @staticmethod
    def is_locked(experiment_id: str, simulation_path: str) -> bool:
        """
        Return whether the simulation is locked.

        A simulation is locked when its manifest file is read-only or when any
        current tuner/production job references its ``simulation_path``.

        Returns:
            True if the simulation is locked.
        """
        # avoid circular dependency
        from .simulation_job import SimulationJob  # noqa: PLC0415
        from .tuner_job import TunerJob  # noqa: PLC0415

        simulation_file = DATA_DIR / experiment_id / simulation_path
        if not os.access(simulation_file, os.W_OK):
            return True

        return bool(
            TunerJob.query.filter_by(experiment_id=experiment_id, simulation_path=simulation_path).first()
            or SimulationJob.query.filter_by(experiment_id=experiment_id, simulation_path=simulation_path).first()
        )

    @staticmethod
    def list_files(experiment_id: str) -> list[FileInfo]:
        """
        Discover `.simulation.json` files under the experiment directory.

        Returns:
            Sorted list of FileInfo objects.
        """
        exp_dir = DATA_DIR / experiment_id
        if not exp_dir.is_dir():
            return []
        files = [f for f in get_files_with_extensions(exp_dir, "json") if f.name.endswith(SIMULATION_SUFFIX)]
        return sorted(files, key=lambda f: f.path)

    @classmethod
    def list(cls, experiment_id: str) -> list["Simulation"]:
        """
        List all simulations with validation status, sorted by path.

        Returns:
            List of Simulation instances (includes invalid/unreadable ones).
        """
        simulations: list[Simulation] = []
        for file_info in cls.list_files(experiment_id):
            sim = cls._from_file(experiment_id, file_info.path)
            simulations.append(sim)
        return simulations

    @classmethod
    def get(cls, experiment_id: str, simulation_path: str) -> "Simulation":
        """
        Get a single simulation by path.

        Returns:
            Simulation instance (includes invalid/unreadable ones).

        Raises:
            NotFound: If the file does not exist.
        """
        sim_path = Path(simulation_path).as_posix()
        check_path(sim_path, DATA_DIR / experiment_id)
        simulation_file = DATA_DIR / experiment_id / sim_path
        if not simulation_file.is_file():
            raise NotFound(description=f"Simulation '{sim_path}' not found.")
        return cls._from_file(experiment_id, sim_path)

    @classmethod
    def _from_file(cls, experiment_id: str, simulation_path: str) -> "Simulation":
        try:
            raw = json.loads((DATA_DIR / experiment_id / simulation_path).read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            return cls(experiment_id, simulation_path, read_error=str(exc))
        return cls(experiment_id, simulation_path, raw=raw)

    @classmethod
    def write(cls, experiment_id: str, payload: dict) -> "Simulation":
        """
        Create a simulation manifest at `{name}.simulation.json` unless a path is provided.

        Returns:
            The created Simulation instance.

        Raises:
            BadRequest: If the path is unsafe, locked, or content is invalid.
        """
        experiment = Experiment.query.get_or_404(experiment_id, description=f"Experiment {experiment_id} not found")
        simulation_path = payload.get("simulation_path") or _safe_default_path(payload.get("name", ""))
        simulation_path = Path(simulation_path).as_posix()
        check_path(simulation_path, DATA_DIR / experiment_id)
        if not simulation_path.endswith(SIMULATION_SUFFIX):
            raise BadRequest(description=f"Path must end with '{SIMULATION_SUFFIX}'.")

        simulation_file = DATA_DIR / experiment_id / simulation_path
        if simulation_file.exists():
            raise BadRequest(description=f"Simulation '{simulation_path}' already exists.")

        content = _build_content(experiment_id, simulation_path, experiment.engine, payload)
        _validate_content_or_raise(experiment_id, simulation_path, content, experiment.engine)

        simulation_file.parent.mkdir(parents=True, exist_ok=True)
        simulation_file.write_text(json.dumps(content, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        return cls(experiment_id, simulation_path, raw=content)

    @classmethod
    def delete(cls, experiment_id: str, simulation_path: str) -> None:
        """
        Delete a simulation manifest and cascade-delete all related jobs.

        Removes TunerJob, SimulationJob, and AnalysisJob records (and their K8s resources), then removes the manifest file. Data files are left untouched.

        Raises:
            BadRequest: If the path is unsafe or does not end with '.simulation.json'.
            NotFound: If the manifest file does not exist.
        """
        # avoid circular dependency
        from .analysis_job import AnalysisJob  # noqa: PLC0415
        from .simulation_job import SimulationJob  # noqa: PLC0415
        from .tuner_job import TunerJob  # noqa: PLC0415

        simulation_path = Path(simulation_path).as_posix()
        check_path(simulation_path, DATA_DIR / experiment_id)
        if not simulation_path.endswith(SIMULATION_SUFFIX):
            raise BadRequest(description=f"Path must end with '{SIMULATION_SUFFIX}'.")
        simulation_file = DATA_DIR / experiment_id / simulation_path
        if not simulation_file.is_file():
            raise NotFound(description=f"Simulation '{simulation_path}' not found.")

        for model in (TunerJob, SimulationJob, AnalysisJob):
            jobs = model.query.filter_by(experiment_id=experiment_id, simulation_path=simulation_path).all()
            for job in jobs:
                job.delete()
                db.session.delete(job)
        db.session.commit()

        try:
            if not os.access(simulation_file, os.W_OK):
                simulation_file.chmod(WRITABLE_MODE)
            simulation_file.unlink()
        except OSError:
            logger.warning("Failed to delete simulation '%s'", simulation_path, exc_info=True)

    @classmethod
    def update(cls, experiment_id: str, simulation_path: str, payload: dict) -> "Simulation":
        """
        Edit an unlocked simulation manifest.

        Returns:
            The updated Simulation instance.

        Raises:
            BadRequest: If the path is unsafe, does not end with '.simulation.json',
                is job-locked, or content is invalid.
            NotFound: If the file does not exist.
        """
        experiment = Experiment.query.get_or_404(experiment_id, description=f"Experiment {experiment_id} not found")
        simulation_path = Path(simulation_path).as_posix()
        check_path(simulation_path, DATA_DIR / experiment_id)
        if not simulation_path.endswith(SIMULATION_SUFFIX):
            raise BadRequest(description=f"Path must end with '{SIMULATION_SUFFIX}'.")
        simulation_file = DATA_DIR / experiment_id / simulation_path
        if not simulation_file.is_file():
            raise NotFound(description=f"Simulation '{simulation_path}' not found.")

        if cls.is_locked(experiment_id, simulation_path):
            raise BadRequest(description=f"Simulation '{simulation_path}' is locked.")

        content = _build_content(experiment_id, simulation_path, experiment.engine, payload)
        _validate_content_or_raise(experiment_id, simulation_path, content, experiment.engine)

        if simulation_file.exists() and not os.access(simulation_file, os.W_OK):
            try:
                simulation_file.chmod(WRITABLE_MODE)
            except OSError:
                logger.warning("Failed to make simulation '%s' writable", simulation_path, exc_info=True)

        simulation_file.write_text(json.dumps(content, indent=2, sort_keys=True) + "\n", encoding="utf-8")

        try:
            simulation_file.chmod(WRITABLE_MODE)
        except OSError:
            logger.warning("Failed to restore writable mode for '%s'", simulation_path, exc_info=True)

        return cls(experiment_id, simulation_path, raw=content)
