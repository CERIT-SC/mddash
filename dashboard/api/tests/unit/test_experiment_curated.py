"""Unit tests for experiment factory curated module support."""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from enums import Engine
from flask import Flask
from models.experiment import Experiment
from notebook_modules import NotebookModule, NotebookModulesCatalog
from sqlalchemy.orm import Session
from werkzeug.exceptions import BadRequest, InternalServerError


def _gmx_module() -> NotebookModule:
    return NotebookModule(id="gromacs-protein", name="Protein", description="d", engine="GMX", path="gromacs/protein")


def _amber_module() -> NotebookModule:
    return NotebookModule(id="amber-protein", name="Protein", description="d", engine="AMBER", path="amber/protein")


def _binder_module() -> NotebookModule:
    return NotebookModule(
        id="binder-gmx",
        name="Binder",
        description="d",
        engine="GMX",
        path=".",
        repository="https://github.com/bioexcel/biobb_wf_md_setup_membrane.git",
    )


def _catalog(modules: list[NotebookModule]) -> NotebookModulesCatalog:
    return NotebookModulesCatalog(modules=tuple(modules))


class TestPrepareEnvCurated:
    """Tests for prepare_env with a curated notebook module ID."""

    def test_curated_uses_selective_checkout_with_module_path(self, tmp_path: Path) -> None:
        """prepare_env with a module ID should selectively check out the module path."""
        catalog = _catalog([_gmx_module()])
        with (
            patch("models.experiment.DATA_DIR", tmp_path),
            patch("models.experiment.download_git_repo") as mock_full,
            patch("models.experiment.download_git_repo_module") as mock_module,
            patch("models.experiment.load_catalog", return_value=catalog),
        ):
            exp_id = Experiment.prepare_env(
                notebooks_repo="https://github.com/default/repo.git",
                engine=Engine.GMX,
                notebook_module_id="gromacs-protein",
            )

            mock_full.assert_not_called()
            mock_module.assert_called_once()
            call_args = mock_module.call_args
            assert call_args.args[1] == "gromacs/protein"
            assert call_args.args[0] == "https://github.com/default/repo.git"
            assert (tmp_path / exp_id).exists()

    def test_curated_rejects_engine_mismatch(self, tmp_path: Path) -> None:
        """A module ID whose engine differs from the experiment engine should raise BadRequest."""
        catalog = _catalog([_gmx_module()])
        with (
            patch("models.experiment.DATA_DIR", tmp_path),
            patch("models.experiment.download_git_repo_module") as mock_module,
            patch("models.experiment.load_catalog", return_value=catalog),
        ):
            with pytest.raises(BadRequest):
                Experiment.prepare_env(
                    notebooks_repo="https://github.com/default/repo.git",
                    engine=Engine.AMBER,
                    notebook_module_id="gromacs-protein",
                )

            mock_module.assert_not_called()

    def test_curated_rejects_unknown_module_id(self, tmp_path: Path) -> None:
        """An unknown module ID should raise BadRequest."""
        catalog = _catalog([_gmx_module()])
        with (
            patch("models.experiment.DATA_DIR", tmp_path),
            patch("models.experiment.download_git_repo_module") as mock_module,
            patch("models.experiment.load_catalog", return_value=catalog),
        ):
            with pytest.raises(BadRequest):
                Experiment.prepare_env(
                    notebooks_repo="https://github.com/default/repo.git",
                    engine=Engine.GMX,
                    notebook_module_id="no-such-module",
                )

            mock_module.assert_not_called()

    def test_curated_cleanup_on_checkout_failure(self, tmp_path: Path) -> None:
        """A checkout failure should remove the partial experiment directory."""
        catalog = _catalog([_gmx_module()])
        with (
            patch("models.experiment.DATA_DIR", tmp_path),
            patch("models.experiment.download_git_repo_module", side_effect=InternalServerError("fail")),
            patch("models.experiment.load_catalog", return_value=catalog),
            pytest.raises(InternalServerError),
        ):
            Experiment.prepare_env(
                notebooks_repo="https://github.com/default/repo.git",
                engine=Engine.GMX,
                notebook_module_id="gromacs-protein",
            )

    def test_custom_mode_without_module_uses_full_clone(self, tmp_path: Path) -> None:
        """Without a module ID, the existing full-clone path is used."""
        with (
            patch("models.experiment.DATA_DIR", tmp_path),
            patch("models.experiment.download_git_repo") as mock_full,
            patch("models.experiment.download_git_repo_module") as mock_module,
            patch("models.experiment.load_catalog", return_value=_catalog([_gmx_module()])),
        ):
            Experiment.prepare_env(
                notebooks_repo="https://github.com/custom/repo.git",
                access_token="tok",
            )

            mock_full.assert_called_once()
            mock_module.assert_not_called()

    def test_root_path_module_uses_full_clone(self, tmp_path: Path) -> None:
        """A module with path '.' should use full clone, not sparse checkout."""
        catalog = _catalog([_binder_module()])
        with (
            patch("models.experiment.DATA_DIR", tmp_path),
            patch("models.experiment.download_git_repo") as mock_full,
            patch("models.experiment.download_git_repo_module") as mock_module,
            patch("models.experiment.load_catalog", return_value=catalog),
        ):
            Experiment.prepare_env(
                notebooks_repo="https://github.com/bioexcel/biobb_wf_md_setup_membrane.git",
                engine=Engine.GMX,
                notebook_module_id="binder-gmx",
            )

            mock_full.assert_called_once()
            mock_module.assert_not_called()


class TestFromPdbCurated:
    """Tests for Experiment.from_pdb with curated modules."""

    def test_from_pdb_curated_stores_default_repo(
        self,
        app: Flask,  # ruff:ignore[unused-method-argument]
        db_session: Session,  # ruff:ignore[unused-method-argument]
        tmp_path: Path,
    ) -> None:
        """Curated from_pdb should store the configured default repository URL."""
        catalog = _catalog([_gmx_module()])
        with (
            patch("models.experiment.requests.get") as mock_get,
            patch("models.experiment.DATA_DIR", tmp_path),
            patch("models.experiment.download_git_repo_module"),
            patch("models.experiment.load_catalog", return_value=catalog),
        ):
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.content = (
                b"ATOM      1  N   ALA A   1       0.000   0.000   0.000  1.00  0.00           N\nEND\n"
            )
            mock_get.return_value = mock_response

            exp = Experiment.from_pdb(
                name="Curated PDB",
                pdb_source="1ABC",
                notebooks_repo="https://github.com/default/repo.git",
                engine=Engine.GMX,
                notebook_module_id="gromacs-protein",
            )

            assert exp.notebooks_repo == "https://github.com/default/repo.git"
            assert (tmp_path / exp.id / "input.pdb").exists()
