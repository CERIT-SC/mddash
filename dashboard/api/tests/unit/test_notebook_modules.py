"""Unit tests for the curated notebook modules catalog."""

import json
from pathlib import Path

import pytest
from jsonschema import ValidationError
from notebook_modules import SCHEMA_PATH, NotebookModule, load_catalog

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

    def test_bundled_catalog_modules_have_display_fields_without_paths(self) -> None:
        """Each bundled module exposes stable display metadata."""
        catalog = load_catalog()

        for module in catalog:
            assert module.id
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

    def test_get_module_returns_matching_module(self) -> None:
        """get_module should return the module with the given ID."""
        catalog = load_catalog()

        module = catalog.get("gromacs-protein")

        assert module is not None
        assert module.engine == "GMX"
        assert module.path == "gromacs/protein"

    def test_get_module_unknown_id_returns_none(self) -> None:
        """get_module should return None for an unknown ID."""
        catalog = load_catalog()

        assert catalog.get("does-not-exist") is None

    def test_get_module_for_engine_returns_matching_module(self) -> None:
        """get_module_for_engine should return a module matching both ID and engine."""
        catalog = load_catalog()

        module = catalog.get_module_for_engine("amber-protein", "AMBER")

        assert module is not None
        assert module.engine == "AMBER"

    def test_get_module_for_engine_rejects_engine_mismatch(self) -> None:
        """get_module_for_engine should return None when engine differs."""
        catalog = load_catalog()

        assert catalog.get_module_for_engine("gromacs-protein", "AMBER") is None

    def test_get_module_for_engine_unknown_id_returns_none(self) -> None:
        """get_module_for_engine should return None for an unknown ID."""
        catalog = load_catalog()

        assert catalog.get_module_for_engine("nope", "GMX") is None

    def test_to_public_excludes_internal_paths(self) -> None:
        """to_public should expose display metadata without internal Git paths."""
        catalog = load_catalog()

        public = catalog.to_public()

        for entry in public:
            assert "id" in entry
            assert "name" in entry
            assert "engine" in entry
            assert "path" not in entry
            assert "repository" not in entry

    def test_to_public_returns_list_of_dicts(self) -> None:
        """to_public should return a JSON-serializable list."""
        catalog = load_catalog()

        public = catalog.to_public()

        assert isinstance(public, list)
        assert len(public) >= MIN_MODULE_COUNT
        # Must be JSON-serializable for the API endpoint
        json.dumps(public)

    def test_load_catalog_caches_default_path(self) -> None:
        """The bundled catalog is memoized, so repeated default loads share one instance."""
        first = load_catalog()
        second = load_catalog()

        assert first is second


class TestModulePathSafety:
    """Tests for module path normalization and safety."""

    def test_module_path_is_relative_posix(self) -> None:
        """Module paths should be forward-slash relative paths."""
        catalog = load_catalog()

        for module in catalog:
            assert not module.path.startswith("/")
            assert "\\" not in module.path
            assert ".." not in module.path.split("/")

    def test_module_resolved_relative_to_dir(self, tmp_path: Path) -> None:
        """resolve_path should produce a path inside the given base directory."""
        module = NotebookModule(id="x", name="X", description=None, engine="GMX", path="gromacs/protein")

        resolved = module.resolve_path(tmp_path)

        assert resolved == tmp_path / "gromacs" / "protein"
        resolved.relative_to(tmp_path)

    def test_module_to_dict_includes_path(self) -> None:
        """The internal module representation includes the path for server-side use."""
        module = NotebookModule(id="x", name="X", description="d", engine="GMX", path="gromacs/protein")

        data = module.to_dict()

        assert data["path"] == "gromacs/protein"
        assert data["engine"] == "GMX"


class TestRepositoryField:
    """Tests for the optional repository field and root-path (Binder) support."""

    def test_bundled_modules_without_repository_default_to_none(self) -> None:
        """Curated modules without an explicit repository should have repository=None."""
        catalog = load_catalog()

        default_repo_modules = [m for m in catalog if m.repository is None]
        assert len(default_repo_modules) >= MIN_MODULE_COUNT

    def test_bundled_repository_modules_present(self) -> None:
        """At least one bundled module should use an explicit repository (Binder)."""
        catalog = load_catalog()

        repo_modules = [m for m in catalog if m.repository is not None]
        assert len(repo_modules) >= 1
        assert all(m.repository and m.is_root for m in repo_modules)

    def test_repository_field_accepted(self, tmp_path: Path) -> None:
        """A module with a repository field should load correctly."""
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

    def test_root_path_allowed(self, tmp_path: Path) -> None:
        """Path '.' should be accepted as the repository root."""
        catalog_file = tmp_path / "notebook-modules.json"
        catalog_file.write_text(
            json.dumps({"modules": [{"id": "root-mod", "name": "Root", "engine": "GMX", "path": "."}]})
        )

        catalog = load_catalog(path=catalog_file)
        module = catalog.get("root-mod")

        assert module is not None
        assert module.is_root is True

    def test_to_dict_includes_repository_when_present(self) -> None:
        """to_dict should include repository when set."""
        module = NotebookModule(
            id="x", name="X", description=None, engine="GMX", path=".", repository="https://example.com/repo.git"
        )

        data = module.to_dict()

        assert data["repository"] == "https://example.com/repo.git"

    def test_to_dict_omits_repository_when_absent(self) -> None:
        """to_dict should not include repository when not set."""
        module = NotebookModule(id="x", name="X", description=None, engine="GMX", path="gromacs/protein")

        data = module.to_dict()

        assert "repository" not in data


class TestBundledSchemaSelfCheck:
    """Ensure the bundled catalog passes its own schema."""

    def test_bundled_schema_file_is_valid_json(self) -> None:
        """The bundled schema file should be valid JSON."""
        data = json.loads(SCHEMA_PATH.read_text())
        assert data["title"] == "Notebook modules catalog"
