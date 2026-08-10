import json
import logging
import os
from contextlib import suppress
from http import HTTPStatus
from pathlib import Path
from typing import Any, NamedTuple

import jsonschema
from cache import step_status_cache
from cachetools import cached
from config import DATA_DIR
from enums import Engine, JobStatus
from errors import ApiError
from extensions import db
from manifest_schema import resolve_schema_url, schema_url
from utils import FileInfo, get_files_with_extensions
from validators import check_path
from werkzeug.exceptions import BadRequest, NotFound

from .experiment import Experiment

logger = logging.getLogger(__name__)

SIMULATION_SUFFIX = ".simulation.json"
READONLY_MODE = 0o444
WRITABLE_MODE = 0o644

ROLE_LABELS: dict[str, str] = {
    "run_input": "Run input",
    "run_structure": "Final run structure",
    "reference_structure": "Reference structure",
    "trajectory": "Trajectory",
    "topology": "Topology",
    "coordinates": "Coordinates",
    "control": "Run control",
}


def property_label(prop: str) -> str:
    """Human-readable label for a manifest property or file role."""
    return ROLE_LABELS.get(prop, prop.replace("_", " ").capitalize())


_HUMAN_TYPES: dict[str, str] = {
    "string": "a text value",
    "object": "a set of key/value entries",
    "array": "a list",
    "integer": "a whole number",
    "number": "a number",
    "boolean": "true or false",
}

_NAME_CHARS = "letters, numbers, '.', '_' and '-'"
_PATH_CHARS = "letters, numbers, '/', '.', '_' and '-'"


def _describe_validation_error(exc: jsonschema.ValidationError) -> str:
    """
    Describe a jsonschema failure in plain English.

    Builds the message from the exception's structured fields (validator,
    validator_value, absolute_path, instance, schema) — never by parsing
    ``exc.message``, whose wording is not a stable API and leaks regexes
    and jsonschema jargon to end users.
    """
    path = [str(p) for p in exc.absolute_path]
    leaf = path[-1] if path else ""
    label = property_label(leaf)
    properties = exc.schema.get("properties", {}) if isinstance(exc.schema, dict) else {}

    match exc.validator:
        case "required":
            missing = sorted(property_label(p) for p in set(exc.validator_value) - set(exc.instance))
            what = "file role" if leaf == "files" else "property"
            return f"Missing required {what}: {', '.join(repr(m) for m in missing)}."
        case "pattern":
            if leaf == "name":
                return f"The simulation name {exc.instance!r} contains unsupported characters — use only {_NAME_CHARS}."
            return (
                f"The path for '{label}' ({exc.instance!r}) contains unsupported characters — use only {_PATH_CHARS}."
            )
        case "not":
            return (
                f"The path for '{label}' must stay inside the experiment folder — "
                "it must not start with '/' or contain '..' or '//'."
            )
        case "const":
            return f"'{label}' must be '{exc.validator_value}'."
        case "type":
            if leaf == "files":
                return "'files' must map file roles to file paths."
            human = _HUMAN_TYPES.get(str(exc.validator_value), str(exc.validator_value))
            return f"'{label}' must be {human}."
        case "additionalProperties":
            extras = sorted(set(exc.instance) - set(properties))
            allowed = sorted(repr(property_label(p)) for p in properties)
            what = "file role" if leaf == "files" else "property"
            return f"Unknown {what} {', '.join(repr(e) for e in extras)} — allowed values: {', '.join(allowed)}."
        case _:
            message = exc.message
            for role, friendly in ROLE_LABELS.items():
                message = message.replace(f"'{role}'", f"'{friendly}'")
            return message


def _safe_default_path(name: str) -> str:
    safe_name = Path(name).name if name else "simulation"
    return f"{safe_name}{SIMULATION_SUFFIX}"


class _JobRows(NamedTuple):
    """Job rows referencing one ``simulation_path`` — the single source of the job-model set."""

    tuner: list[Any]
    simulation: list[Any]
    analysis: list[Any]


def _query_jobs(experiment_id: str, simulation_path: str) -> _JobRows:
    """Scan every job table for a simulation in one call."""
    # avoid circular dependency
    from .analysis_job import AnalysisJob  # ruff:ignore[import-outside-top-level]
    from .simulation_job import SimulationJob  # ruff:ignore[import-outside-top-level]
    from .tuner_job import TunerJob  # ruff:ignore[import-outside-top-level]

    def rows(model: Any) -> list[Any]:  # ruff:ignore[any-type]
        return model.query.filter_by(experiment_id=experiment_id, simulation_path=simulation_path).all()

    return _JobRows(tuner=rows(TunerJob), simulation=rows(SimulationJob), analysis=rows(AnalysisJob))


def _build_content(engine: Engine, payload: dict) -> dict:
    files = payload.get("files")
    if not isinstance(files, dict):
        raise BadRequest(description="'files' must map file roles to file paths.")

    return {
        "$schema": schema_url(engine),
        "name": payload.get("name", ""),
        "engine": engine.value,
        "files": files,
        "extra_args": payload.get("extra_args", ""),
    }


def _validate_content_or_raise(content: dict, engine: Engine) -> None:
    schema = resolve_schema_url(content.get("$schema"))
    if schema is None:
        raise BadRequest(
            description="The simulation file does not declare its format ('$schema' is missing or invalid), so it cannot be validated."
        )
    try:
        jsonschema.validate(content, schema)
    except jsonschema.ValidationError as exc:
        raise BadRequest(description=f"Simulation content is invalid: {_describe_validation_error(exc)}") from exc

    if content.get("engine") != engine.value:
        raise BadRequest(
            description=f"The simulation engine '{content.get('engine')}' does not match the experiment's '{engine.value}' engine."
        )


class Simulation:  # ruff:ignore[too-many-public-methods]
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
        self._memo_jobs: _JobRows | None = None

    def _cached_jobs(self) -> _JobRows:
        """Job rows for this simulation, queried once per instance."""
        if self._memo_jobs is None:
            self._memo_jobs = _query_jobs(self.experiment_id, self.simulation_path)
        return self._memo_jobs

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
        if not os.access(self._file, os.W_OK):
            return True
        jobs = self._cached_jobs()
        return bool(jobs.tuner or jobs.simulation)

    @property
    def last_activity(self) -> float:
        """
        Epoch seconds of the most recent interaction with this simulation.

        Latest of manifest mtime, simulation-job creation/start/finish, and
        tuner/analysis-job creation. Job start/finish are only set once the
        MDRun API reports them, hence creation time for fresh jobs. Analysis
        counts here (moves the 'latest' pointer) but not in the step ladder —
        that only advances on a finished MD job.
        """
        events: list[float] = []
        with suppress(OSError):
            events.append(self._file.stat().st_mtime)
        jobs = self._cached_jobs()
        for job in jobs.simulation:
            timestamps = (job._start_timestamp, job._finish_timestamp)  # ruff:ignore[private-member-access]
            events.extend(float(t) for t in timestamps if t is not None)
            if job.created_at is not None:
                events.append(job.created_at.timestamp())
        for job in (*jobs.tuner, *jobs.analysis):
            if job.created_at is not None:
                events.append(job.created_at.timestamp())
        return max(events, default=0.0)

    @property
    def step(self) -> int:
        """Wizard step of this simulation based on its own jobs and manifest validity."""
        return self._step_status()[0]

    @property
    def status(self) -> str:
        """Status of this simulation based on its own jobs and manifest validity."""
        return self._step_status()[1]

    @property
    def step_status(self) -> tuple[int, str]:
        """Per-simulation (step, status) ladder; public accessor for the cached method."""
        return self._step_status()

    @cached(cache=step_status_cache)
    def _step_status(self) -> tuple[int, str]:
        """
        (step, status) from jobs referencing this ``simulation_path``.

        Finished job (4), running job (3), any job or tuned trial (2), any
        tuner job (1), valid manifest (1), otherwise 0. Publish is
        experiment-level and not part of this ladder.

        Returns:
            A tuple of (step, status) where step is an integer (0-4) and status
            is a string describing the current phase.
        """
        jobs = self._cached_jobs()

        if any(j.status == JobStatus.FINISHED for j in jobs.simulation):
            return 4, "analyzing"
        if any(j.status == JobStatus.RUNNING for j in jobs.simulation):
            return 3, "simulating"
        if jobs.simulation:
            return 2, "simulating"

        if any(any(t.get("performance") is not None for t in j.trials) for j in jobs.tuner):
            return 2, "tuning"
        if jobs.tuner:
            return 1, "tuning"

        if self.valid:
            return 1, "setup complete"
        return 0, "setup"

    def to_dict(self) -> dict:
        """
        Serialize to the API response dict.

        Returns:
            Dict with simulation_path, name, engine, files, resolved_files,
            extra_args, locked, valid, errors, missing_files, step, status.
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
            "step": self.step,
            "status": self.status,
            "last_activity": self.last_activity,
        }

    def resolve_role(self, role: str) -> Path:
        """
        Resolve a file role to an absolute Path.

        Roles are resolved relative to the experiment directory, consistent with
        ``resolved_files`` and the manifest writer convention.

        Returns:
            Absolute Path to the role file.

        Raises:
            BadRequest: If the role is absent or points outside the experiment folder.
        """
        rel = self.files.get(role)
        if not isinstance(rel, str) or not rel:
            raise BadRequest(description=f"The simulation does not define a '{property_label(role)}' file.")
        exp_dir = (DATA_DIR / self.experiment_id).resolve()
        resolved = (exp_dir / rel).resolve()
        try:
            resolved.relative_to(exp_dir)
        except ValueError as exc:
            raise BadRequest(
                description=f"The '{property_label(role)}' path points outside the experiment folder."
            ) from exc
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
            raise BadRequest(
                description=f"Missing files for: {', '.join(repr(property_label(r)) for r in missing_files)}."
            )

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
            self._validation = (
                False,
                [
                    f"This simulation file could not be read — it may have been deleted or corrupted. ({self._read_error})"
                ],
                [],
            )
            return self._validation

        errors: list[str] = []
        resolved = self.resolved_files
        exp_dir = DATA_DIR / self.experiment_id

        schema = resolve_schema_url(self._raw.get("$schema"))
        if schema is None:
            errors.append(
                "The simulation file does not declare its format ('$schema' is missing or invalid), so it cannot be validated."
            )
        else:
            try:
                jsonschema.validate(self._raw, schema)
            except jsonschema.ValidationError as exc:
                errors.append(_describe_validation_error(exc))

        experiment = db.session.get(Experiment, self.experiment_id)
        if experiment is not None:
            sim_engine = self._raw.get("engine")
            if sim_engine != experiment.engine.value:
                errors.append(
                    f"The simulation engine '{sim_engine}' does not match the experiment's '{experiment.engine.value}' engine."
                )

        for role, rel in resolved.items():
            if rel and rel.startswith("/"):
                errors.append(
                    f"The path for '{property_label(role)}' must be relative to the experiment folder (it must not start with '/')."
                )

        missing = [role for role, rel in resolved.items() if not (exp_dir / rel).is_file()]

        self._validation = not errors, errors, missing
        return self._validation

    @staticmethod
    def is_locked(experiment_id: str, simulation_path: str) -> bool:
        """
        Return whether the simulation is locked.

        A simulation is locked when its manifest file is read-only or when any
        current tuner/production job references its ``simulation_path``.

        Returns:
            True if the simulation is locked.
        """
        simulation_file = DATA_DIR / experiment_id / simulation_path
        if not os.access(simulation_file, os.W_OK):
            return True

        jobs = _query_jobs(experiment_id, simulation_path)
        return bool(jobs.tuner or jobs.simulation)

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
    def _require_unique_name(cls, experiment_id: str, name: str, exclude_path: str | None = None) -> None:
        """
        Reject a name already used by another manifest in this experiment.

        Names are the wizard tab identity (``?tab=<name>``), hence unique.
        Underscore prefixes are reserved for UI sentinels (``_new`` = create tab).

        Raises:
            ApiError: 409 when the name is reserved or already taken.
        """
        if not name:
            return
        if name.startswith("_"):
            raise ApiError(
                HTTPStatus.CONFLICT,
                f"The simulation name '{name}' is reserved.",
                "urn:mddash:duplicate-simulation-name",
                "Choose a different name.",
            )
        for file_info in cls.list_files(experiment_id):
            if exclude_path is not None and Path(file_info.path).as_posix() == exclude_path:
                continue
            other = cls._from_file(experiment_id, file_info.path)
            if other.name == name:
                raise ApiError(
                    HTTPStatus.CONFLICT,
                    f"A simulation named '{name}' already exists.",
                    "urn:mddash:duplicate-simulation-name",
                    "Choose a different name.",
                )

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
            display_name = payload.get("name") or simulation_path.removesuffix(SIMULATION_SUFFIX)
            raise BadRequest(description=f"Simulation '{display_name}' already exists.")

        content = _build_content(experiment.engine, payload)
        _validate_content_or_raise(content, experiment.engine)
        cls._require_unique_name(experiment_id, str(content.get("name", "")))

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
        simulation_path = Path(simulation_path).as_posix()
        check_path(simulation_path, DATA_DIR / experiment_id)
        if not simulation_path.endswith(SIMULATION_SUFFIX):
            raise BadRequest(description=f"Path must end with '{SIMULATION_SUFFIX}'.")
        simulation_file = DATA_DIR / experiment_id / simulation_path
        if not simulation_file.is_file():
            raise NotFound(description=f"Simulation '{simulation_path}' not found.")

        jobs = _query_jobs(experiment_id, simulation_path)
        for job in (*jobs.tuner, *jobs.simulation, *jobs.analysis):
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
            raise ApiError(
                HTTPStatus.BAD_REQUEST,
                f"Simulation '{simulation_path}' is locked.",
                "urn:mddash:simulation-locked",
                "This simulation is in use by a running job; stop the job before editing it.",
            )

        content = _build_content(experiment.engine, payload)
        _validate_content_or_raise(content, experiment.engine)
        cls._require_unique_name(experiment_id, str(content.get("name", "")), exclude_path=simulation_path)

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
