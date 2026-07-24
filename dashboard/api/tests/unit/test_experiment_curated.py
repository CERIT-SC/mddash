"""Unit tests for experiment factory curated module support."""

from pathlib import Path
from unittest.mock import patch

import pytest
from models.experiment import Experiment
from notebook_modules import NotebookModule
from werkzeug.exceptions import InternalServerError


def _gmx_module() -> NotebookModule:
    return NotebookModule(id="gromacs-protein", name="Protein", description="d", engine="GMX", path="gromacs/protein")


def _binder_module() -> NotebookModule:
    return NotebookModule(
        id="binder-gmx",
        name="Binder",
        description="d",
        engine="GMX",
        path=".",
        repository="https://github.com/bioexcel/biobb_wf_md_setup_membrane.git",
    )


class TestPrepareEnvCurated:
    """Tests for prepare_env with a curated notebook module."""

    def test_curated_uses_selective_checkout_with_module_path(self, tmp_path: Path) -> None:
        """prepare_env with a module should selectively check out the module path."""
        with (
            patch("models.experiment.DATA_DIR", tmp_path),
            patch("models.experiment.download_git_repo") as mock_full,
            patch("models.experiment.download_git_repo_module") as mock_module,
        ):
            exp_id = Experiment.prepare_env(
                notebooks_repo="https://github.com/default/repo.git",
                notebook_module=_gmx_module(),
            )

            mock_full.assert_not_called()
            mock_module.assert_called_once()
            assert mock_module.call_args.args[1] == "gromacs/protein"
            assert (tmp_path / exp_id).exists()

    def test_curated_cleanup_on_checkout_failure(self, tmp_path: Path) -> None:
        """A checkout failure should remove the partial experiment directory."""
        with (
            patch("models.experiment.DATA_DIR", tmp_path),
            patch("models.experiment.download_git_repo_module", side_effect=InternalServerError("fail")),
            pytest.raises(InternalServerError),
        ):
            Experiment.prepare_env(
                notebooks_repo="https://github.com/default/repo.git",
                notebook_module=_gmx_module(),
            )

    def test_root_path_module_uses_full_clone(self, tmp_path: Path) -> None:
        """A module with path '.' should use full clone, not sparse checkout."""
        with (
            patch("models.experiment.DATA_DIR", tmp_path),
            patch("models.experiment.download_git_repo") as mock_full,
            patch("models.experiment.download_git_repo_module") as mock_module,
        ):
            Experiment.prepare_env(
                notebooks_repo="https://github.com/bioexcel/biobb_wf_md_setup_membrane.git",
                notebook_module=_binder_module(),
            )

            mock_full.assert_called_once()
            mock_module.assert_not_called()
