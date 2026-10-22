"""Unit tests for experiment factory curated module support."""

from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
from clients import Clients
from core.errors import InternalServerError
from modules.experiments.service import ExperimentService
from modules.notebooks.catalog import NotebookModule


def _gmx_module() -> NotebookModule:
    return NotebookModule(
        id="gromacs-protein",
        name="Protein",
        description="d",
        engine="GMX",
        author="a",
        category="protein",
        path="gromacs/protein",
    )


def _binder_module() -> NotebookModule:
    return NotebookModule(
        id="binder-gmx",
        name="Binder",
        description="d",
        engine="GMX",
        author="a",
        category="protein",
        path=".",
        repository="https://github.com/bioexcel/biobb_wf_md_setup_membrane.git",
    )


class TestPrepareEnvCurated:
    """Tests for prepare_env with a curated notebook module."""

    async def test_curated_uses_selective_checkout_with_module_path(self, tmp_path: Path, clients: Clients) -> None:
        """prepare_env with a module should selectively check out the module path."""
        with (
            patch.object(clients.git, "clone") as mock_full,
            patch.object(clients.git, "clone_module") as mock_module,
        ):
            exp_id = await ExperimentService(AsyncMock(), clients).prepare_env(
                notebooks_repo="https://github.com/default/repo.git",
                notebook_module=_gmx_module(),
            )

            mock_full.assert_not_called()
            mock_module.assert_called_once()
            assert mock_module.call_args.args[1] == "gromacs/protein"
            assert (tmp_path / exp_id).exists()

    async def test_curated_cleanup_on_checkout_failure(self, tmp_path: Path, clients: Clients) -> None:
        """A checkout failure should remove the partial experiment directory."""
        with (
            patch.object(clients.git, "clone_module", side_effect=InternalServerError("fail")),
            pytest.raises(InternalServerError),
        ):
            await ExperimentService(AsyncMock(), clients).prepare_env(
                notebooks_repo="https://github.com/default/repo.git",
                notebook_module=_gmx_module(),
            )

    async def test_root_path_module_uses_full_clone(self, tmp_path: Path, clients: Clients) -> None:
        """A module with path '.' should use full clone, not sparse checkout."""
        with (
            patch.object(clients.git, "clone") as mock_full,
            patch.object(clients.git, "clone_module") as mock_module,
        ):
            await ExperimentService(AsyncMock(), clients).prepare_env(
                notebooks_repo="https://github.com/bioexcel/biobb_wf_md_setup_membrane.git",
                notebook_module=_binder_module(),
            )

            mock_full.assert_called_once()
            mock_module.assert_not_called()
