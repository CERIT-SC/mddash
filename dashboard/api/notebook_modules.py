"""Curated notebook modules catalog bundled with the Dashboard API."""

import json
import logging
from collections.abc import Iterator
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import overload

from jsonschema import Draft202012Validator, FormatChecker
from jsonschema import ValidationError as JsonSchemaValidationError

logger = logging.getLogger(__name__)

_MODULE_DIR = Path(__file__).resolve().parent
CATALOG_PATH = _MODULE_DIR / "notebook-modules.json"
SCHEMA_PATH = _MODULE_DIR / "notebook-modules.schema.json"

ROOT_PATH = "."


@dataclass(frozen=True)
class NotebookModule:
    """A single curated notebook module entry."""

    id: str
    name: str
    description: str | None
    engine: str
    path: str
    repository: str | None = None

    @property
    def is_root(self) -> bool:
        """True when path is '.', meaning full clone (preserves root Binder config)."""
        return self.path == ROOT_PATH

    def to_public(self) -> dict:
        """
        Display metadata for the UI, excluding internal Git paths.

        Returns:
            A dictionary with id, name, engine, and optional description.
        """
        data: dict = {"id": self.id, "name": self.name, "engine": self.engine}
        if self.description is not None:
            data["description"] = self.description
        return data


@dataclass(frozen=True)
class NotebookModulesCatalog:
    """Validated collection of curated notebook modules."""

    modules: tuple[NotebookModule, ...]

    @overload
    def get(self, module_id: str) -> NotebookModule | None: ...

    @overload
    def get(self, module_id: str, engine: str) -> NotebookModule | None: ...

    def get(self, module_id: str, engine: str | None = None) -> NotebookModule | None:
        """
        Return the module with the given ID, optionally requiring a matching engine.

        Returns:
            The matching module, or None.
        """
        for module in self.modules:
            if module.id == module_id:
                if engine is None or module.engine == engine:
                    return module
                return None
        return None

    def get_module_for_engine(self, module_id: str, engine: str) -> NotebookModule | None:
        """
        Return the module matching both ID and engine.

        Returns:
            The matching module, or None.
        """
        return self.get(module_id, engine)

    def to_public(self) -> list[dict]:
        """
        Return display metadata for all modules, excluding internal Git paths.

        Returns:
            A list of public module dictionaries.
        """
        return [m.to_public() for m in self.modules]

    def __iter__(self) -> Iterator[NotebookModule]:
        return iter(self.modules)


def _load_schema() -> dict:
    return json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))


def _build_catalog(data: dict) -> NotebookModulesCatalog:
    """
    Construct a NotebookModulesCatalog from validated raw data, enforcing unique IDs.

    Returns:
        The validated NotebookModulesCatalog.

    Raises:
        ValueError: If module IDs are not unique.
    """
    modules: list[NotebookModule] = []
    seen_ids: set[str] = set()
    for raw in data["modules"]:
        module_id = raw["id"]
        if module_id in seen_ids:
            raise ValueError(f"Duplicate notebook module id: {module_id}")
        seen_ids.add(module_id)
        modules.append(
            NotebookModule(
                id=module_id,
                name=raw["name"],
                description=raw.get("description"),
                engine=raw["engine"],
                path=raw["path"],
                repository=raw.get("repository"),
            )
        )
    return NotebookModulesCatalog(modules=tuple(modules))


@lru_cache(maxsize=1)
def load_catalog(path: Path | None = None) -> NotebookModulesCatalog:
    """
    Load and validate the curated notebook modules catalog from the bundled JSON file.

    Returns:
        The validated NotebookModulesCatalog.
    """
    catalog_path = path or CATALOG_PATH
    raw = json.loads(catalog_path.read_text(encoding="utf-8"))
    schema = _load_schema()
    Draft202012Validator(schema, format_checker=FormatChecker()).validate(raw)
    return _build_catalog(raw)


def load_catalog_or_exit(path: Path | None = None) -> NotebookModulesCatalog:
    """
    Load the catalog or exit with a fatal error. Used at startup.

    Returns:
        The validated NotebookModulesCatalog.

    Raises:
        SystemExit: If the catalog cannot be loaded or validated.
    """
    try:
        return load_catalog(path)
    except (FileNotFoundError, JsonSchemaValidationError, ValueError, json.JSONDecodeError) as exc:
        logger.critical("Failed to load notebook modules catalog: %s", exc)
        raise SystemExit(1) from exc
