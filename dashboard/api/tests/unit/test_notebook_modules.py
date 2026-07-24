"""Unit tests for the curated notebook modules catalog."""

import json
from pathlib import Path

import pytest
from jsonschema import ValidationError
from notebook_modules import load_catalog

MIN_MODULE_COUNT = 2


def _catalog_json(modules: list[dict]) -> str:
    """
    Serialize a minimal catalog document with the given modules list.

    Returns:
        A JSON string with only the ``modules`` key set.
    """
    return json.dumps({"modules": modules})


class TestLoadCatalog:
    """Tests for load_catalog (bundled catalog loading and validation)."""

    def test_loads_bundled_catalog_and_returns_modules(self) -> None:
        """The bundled catalog should load and yield the curated protein modules."""
        catalog = load_catalog()

        ids = {m.id for m in catalog}
        assert "gromacs-protein" in ids
        assert "amber-protein" in ids
        for module in catalog:
            assert module.name
            assert module.engine in {"GMX", "AMBER"}

    def test_unknown_property_rejected(self, tmp_path: Path) -> None:
        """An unknown top-level property should fail validation."""
        catalog_file = tmp_path / "notebook-modules.json"
        catalog_file.write_text(json.dumps({"modules": [], "unknown_field": True}))

        with pytest.raises(ValidationError):
            load_catalog(path=catalog_file)

    def test_duplicate_module_ids_rejected(self, tmp_path: Path) -> None:
        """Duplicate module IDs should fail validation."""
        module = {"id": "dup", "name": "Dup", "engine": "GMX", "path": "gromacs/dup"}
        catalog_file = tmp_path / "notebook-modules.json"
        catalog_file.write_text(_catalog_json([module, module]))

        with pytest.raises(ValueError, match=r"(?i)duplicate"):
            load_catalog(path=catalog_file)

    def test_unknown_engine_rejected(self, tmp_path: Path) -> None:
        """An engine outside the allowed enum should fail validation."""
        catalog_file = tmp_path / "notebook-modules.json"
        catalog_file.write_text(_catalog_json([{"id": "x", "name": "X", "engine": "NAMD", "path": "x/y"}]))

        with pytest.raises(ValidationError):
            load_catalog(path=catalog_file)

    def test_unsafe_path_rejected(self, tmp_path: Path) -> None:
        """A path containing traversal or leading slash should fail validation."""
        catalog_file = tmp_path / "notebook-modules.json"
        catalog_file.write_text(_catalog_json([{"id": "x", "name": "X", "engine": "GMX", "path": "../escape"}]))

        with pytest.raises(ValidationError):
            load_catalog(path=catalog_file)

    def test_empty_modules_rejected(self, tmp_path: Path) -> None:
        """An empty modules list should fail validation."""
        catalog_file = tmp_path / "notebook-modules.json"
        catalog_file.write_text(_catalog_json([]))

        with pytest.raises(ValidationError):
            load_catalog(path=catalog_file)

    def test_missing_catalog_file_raises(self, tmp_path: Path) -> None:
        """A missing catalog file should raise FileNotFoundError."""
        with pytest.raises(FileNotFoundError):
            load_catalog(path=tmp_path / "missing.json")


class TestCatalogLookup:
    """Tests for resolving modules by ID and engine."""

    def test_get_returns_matching_module_and_none_for_misses(self) -> None:
        """Get returns the module for a known ID, None for unknown or engine mismatch."""
        catalog = load_catalog()

        assert catalog.get("gromacs-protein") is not None
        assert catalog.get("does-not-exist") is None
        assert catalog.get_module_for_engine("gromacs-protein", "GMX") is not None
        assert catalog.get_module_for_engine("gromacs-protein", "AMBER") is None
        assert catalog.get_module_for_engine("nope", "GMX") is None

    def test_to_public_excludes_internal_paths_and_is_serializable(self) -> None:
        """to_public should expose display metadata without paths, and be JSON-serializable."""
        catalog = load_catalog()

        public = catalog.to_public()

        assert isinstance(public, list)
        for entry in public:
            assert "id" in entry
            assert "name" in entry
            assert "engine" in entry
            assert "path" not in entry
            assert "repository" not in entry
        json.dumps(public)


class TestRepositoryField:
    """Tests for the optional repository field and root-path (Binder) support."""

    def test_bundled_modules_split_between_default_and_explicit_repos(self) -> None:
        """Bundled catalog has modules with and without explicit repository URLs."""
        catalog = load_catalog()

        default_repo = [m for m in catalog if m.repository is None]
        explicit_repo = [m for m in catalog if m.repository is not None]
        assert len(default_repo) >= MIN_MODULE_COUNT
        assert len(explicit_repo) >= 1
        assert all(m.is_root for m in explicit_repo)

    def test_repository_field_and_root_path_accepted(self, tmp_path: Path) -> None:
        """A module with a repository field and path '.' should load as a root module."""
        catalog_file = tmp_path / "notebook-modules.json"
        catalog_file.write_text(
            json.dumps({
                "modules": [
                    {
                        "id": "binder-gmx",
                        "name": "Binder",
                        "engine": "GMX",
                        "path": ".",
                        "repository": "https://github.com/bioexcel/biobb_wf_md_setup_membrane.git",
                    }
                ]
            })
        )

        catalog = load_catalog(path=catalog_file)
        module = catalog.get("binder-gmx")

        assert module is not None
        assert module.repository == "https://github.com/bioexcel/biobb_wf_md_setup_membrane.git"
        assert module.is_root is True
