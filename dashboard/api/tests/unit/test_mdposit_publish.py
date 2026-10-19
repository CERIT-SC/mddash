"""Unit tests for MDPosit-aware publish routing and from_repo logic."""

import json
import re
from collections.abc import Iterator
from http import HTTPStatus
from pathlib import Path
from unittest.mock import Mock, patch

import pytest
from clients import Clients
from core.enums import Engine
from core.errors import BadRequest
from httpx import AsyncClient
from modules.experiments.service import ExperimentService
from modules.mdrepo.tokens import MDRepoCredentials
from modules.models import Experiment, Notebook
from modules.publishing.service import PublishingService
from modules.publishing.status import UploadStatus
from modules.simulations.manifest_schema import schema_url
from sqlalchemy.ext.asyncio import AsyncSession

GMX_SCHEMA_URL = schema_url(Engine.GMX)
CREDENTIALS = MDRepoCredentials(access_token="valid-token", refresh_token="", expires_at="0")


@pytest.fixture(autouse=True)
def _mdposit_configured() -> Iterator[None]:
    """Ensure MDPOSIT_URL is set for all tests in this module unless overridden."""
    with patch("modules.publishing.mdposit.MDPOSIT_URL", "https://mdposit.example.com"):
        yield


async def _seed_experiment(
    db_session: AsyncSession, exp_id: str = "pubsh", name: str = "Publish Test", **columns: object
) -> Experiment:
    """Persist a minimal experiment with notebook and load it the way a request would."""
    db_session.add(Experiment(id=exp_id, name=name, notebooks_repo="https://github.com/t/r.git", **columns))
    db_session.add(Notebook(experiment_id=exp_id))
    await db_session.commit()
    db_session.expunge_all()
    experiment = await db_session.get(Experiment, exp_id)
    assert experiment is not None
    return experiment


async def _stored(db_session: AsyncSession, exp_id: str = "pubsh") -> Experiment:
    db_session.expunge_all()
    experiment = await db_session.get(Experiment, exp_id)
    assert experiment is not None
    return experiment


def _write_gmx_simulation(
    exp_dir: Path,
    simulation_path: str = "sim.simulation.json",
    name: str = "sim",
    files: dict[str, str] | None = None,
) -> str:
    """
    Write a GMX simulation manifest.

    Returns:
        The simulation_path.
    """
    sim_file = exp_dir / simulation_path
    sim_file.parent.mkdir(parents=True, exist_ok=True)
    content = {
        "$schema": GMX_SCHEMA_URL,
        "name": name,
        "engine": "GMX",
        "files": files or {"run_input": "topol.tpr", "reference_structure": "struct.pdb", "trajectory": "traj.xtc"},
        "extra_args": "",
    }
    sim_file.write_text(json.dumps(content))
    return simulation_path


class TestDefaultPublishTargetInvenio:
    """Default target=invenio requires MDRepo authentication."""

    async def test_publish_default_target_requires_mdrepo_token(
        self, client: AsyncClient, db_session: AsyncSession, tmp_path: Path
    ) -> None:
        """Test test_publish_default_target_requires_mdrepo_token."""
        await _seed_experiment(db_session)
        (tmp_path / "pubsh").mkdir(parents=True, exist_ok=True)

        resp = await client.post("/dash/api/experiments/pubsh/publish")
        assert resp.status_code == HTTPStatus.UNAUTHORIZED
        assert "MDRepo" in resp.json()["detail"]

    async def test_publish_explicit_invenio_also_requires_token(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        tmp_path: Path,
        clients: Clients,
    ) -> None:
        """Test test_publish_explicit_invenio_also_requires_token."""
        await _seed_experiment(db_session)
        (tmp_path / "pubsh").mkdir(parents=True, exist_ok=True)

        resp = await client.post("/dash/api/experiments/pubsh/publish", json={"target": "invenio"})
        assert resp.status_code == HTTPStatus.UNAUTHORIZED

    @patch("modules.publishing.submission.is_upload_active", return_value=False)
    @patch("modules.publishing.service.submit_upload_job", return_value="attempt-001")
    @patch("modules.publishing.submission.read_status", return_value=None)
    @patch("clients.mdrepo.MDRepoClient.create_experiment", return_value={"id": "rec-001"})
    @patch("clients.metadump.MetadumpClient.extract_metadata_bulk", return_value=[])
    async def test_publish_invenio_with_token_succeeds(
        self,
        mock_meta: Mock,
        mock_create: Mock,
        mock_read_status: Mock,
        mock_submit: Mock,
        mock_active: Mock,
        db_session: AsyncSession,
        tmp_path: Path,
        clients: Clients,
    ) -> None:
        """Test test_publish_invenio_with_token_succeeds."""
        await _seed_experiment(db_session)
        (tmp_path / "pubsh").mkdir(parents=True, exist_ok=True)

        exp = await _stored(db_session)
        result = await PublishingService(db_session, clients).publish_invenio(exp, CREDENTIALS)

        assert result["id"] == "rec-001"
        assert result["upload_state"] == "queued"
        mock_create.assert_called_once()


class TestMdpositPublishNoOAuth:
    """MDPosit publish does not require MDRepo OAuth token."""

    async def test_mdposit_publish_does_not_require_mdrepo_token(
        self, client: AsyncClient, db_session: AsyncSession, tmp_path: Path
    ) -> None:
        """Test test_mdposit_publish_does_not_require_mdrepo_token."""
        await _seed_experiment(db_session)
        exp_dir = tmp_path / "pubsh"
        exp_dir.mkdir(parents=True, exist_ok=True)
        (exp_dir / "struct.pdb").write_text("ATOM data")
        (exp_dir / "topol.tpr").write_bytes(b"\x00" * 16)
        (exp_dir / "traj.xtc").write_bytes(b"\x00" * 16)
        sim_path = _write_gmx_simulation(
            exp_dir,
            files={"run_input": "topol.tpr", "reference_structure": "struct.pdb", "trajectory": "traj.xtc"},
        )

        with (
            patch("modules.publishing.mdposit.MDPOSIT_VRE_LITE_URL", "https://mdposit.example.com/vre_lite/"),
        ):
            resp = await client.post(
                "/dash/api/experiments/pubsh/publish", json={"target": "mdposit", "simulation_path": sim_path}
            )
            assert resp.status_code == HTTPStatus.CREATED
            data = resp.json()
            assert "metadata_file" in data
            assert "files" in data
            assert len(data["files"]) == len({"structure", "topology", "trajectory"})
            assert "vre_lite_url" in data

    async def test_mdposit_publish_rejected_when_not_configured(
        self, client: AsyncClient, db_session: AsyncSession, tmp_path: Path
    ) -> None:
        """Test test_mdposit_publish_rejected_when_not_configured."""
        await _seed_experiment(db_session)
        exp_dir = tmp_path / "pubsh"
        exp_dir.mkdir(parents=True, exist_ok=True)
        (exp_dir / "struct.pdb").write_text("ATOM data")
        (exp_dir / "topol.tpr").write_bytes(b"\x00" * 16)
        (exp_dir / "traj.xtc").write_bytes(b"\x00" * 16)
        sim_path = _write_gmx_simulation(exp_dir)

        with (
            patch("modules.publishing.mdposit.MDPOSIT_URL", ""),
        ):
            resp = await client.post(
                "/dash/api/experiments/pubsh/publish", json={"target": "mdposit", "simulation_path": sim_path}
            )
            assert resp.status_code == HTTPStatus.BAD_REQUEST


class TestMdpositPublishNoDbMutation:
    """MDPosit handoff is stateless — must not change MDRepo columns."""

    async def test_mdposit_publish_leaves_mdrepo_fields_null(
        self, db_session: AsyncSession, tmp_path: Path, clients: Clients
    ) -> None:
        """Test test_mdposit_publish_leaves_mdrepo_fields_null."""
        await _seed_experiment(db_session)
        exp_dir = tmp_path / "pubsh"
        exp_dir.mkdir(parents=True, exist_ok=True)
        (exp_dir / "struct.gro").write_text("gro data")
        (exp_dir / "topol.tpr").write_bytes(b"\x00" * 16)
        (exp_dir / "traj.xtc").write_bytes(b"\x00" * 16)
        sim_path = _write_gmx_simulation(
            exp_dir, files={"run_input": "topol.tpr", "reference_structure": "struct.gro", "trajectory": "traj.xtc"}
        )

        with (
            patch("modules.publishing.mdposit.MDPOSIT_VRE_LITE_URL", "https://mdposit.example.com/vre_lite/"),
        ):
            exp = await _stored(db_session)
            assert exp.mdrepo_id is None
            assert exp.mdrepo_published is None

            result = await PublishingService(db_session, clients).publish_mdposit(exp, sim_path)

            exp = await _stored(db_session)
            assert exp.mdrepo_id is None
            assert exp.mdrepo_published is None
            assert "metadata_file" in result
            assert result["metadata_file"]["path"] == "inputs.yaml"

    async def test_mdposit_publish_does_not_overwrite_existing_mdrepo_fields(
        self,
        db_session: AsyncSession,
        tmp_path: Path,
        clients: Clients,
    ) -> None:
        """Test test_mdposit_publish_does_not_overwrite_existing_mdrepo_fields."""
        await _seed_experiment(db_session)
        exp_dir = tmp_path / "pubsh"
        exp_dir.mkdir(parents=True, exist_ok=True)
        (exp_dir / "struct.pdb").write_text("ATOM")
        (exp_dir / "topol.tpr").write_bytes(b"\x00" * 16)
        (exp_dir / "traj.xtc").write_bytes(b"\x00" * 16)
        sim_path = _write_gmx_simulation(exp_dir)

        with (
            patch("modules.publishing.mdposit.MDPOSIT_VRE_LITE_URL", ""),
        ):
            exp = await _stored(db_session)
            exp.mdrepo_id = "existing-mdrepo-id"
            exp.mdrepo_published = True
            await db_session.commit()

            await PublishingService(db_session, clients).publish_mdposit(exp, sim_path)

            exp = await _stored(db_session)
            assert exp.mdrepo_id == "existing-mdrepo-id"
            assert exp.mdrepo_published is True


class TestInvenioPublishUnchanged:
    """Invenio publish still sets mdrepo_id and mdrepo_published=False."""

    @patch("modules.publishing.submission.is_upload_active", return_value=False)
    @patch("modules.publishing.service.submit_upload_job", return_value="attempt-999")
    @patch("modules.publishing.submission.read_status", return_value=None)
    @patch("clients.mdrepo.MDRepoClient.create_experiment", return_value={"id": "rec-999"})
    @patch("clients.metadump.MetadumpClient.extract_metadata_bulk", return_value=[])
    async def test_invenio_publish_sets_mdrepo_fields(
        self,
        mock_meta: Mock,
        mock_create: Mock,
        mock_read_status: Mock,
        mock_submit: Mock,
        mock_active: Mock,
        db_session: AsyncSession,
        tmp_path: Path,
        clients: Clients,
    ) -> None:
        """Test test_invenio_publish_sets_mdrepo_fields."""
        await _seed_experiment(db_session)
        (tmp_path / "pubsh").mkdir(parents=True, exist_ok=True)

        exp = await _stored(db_session)
        result = await PublishingService(db_session, clients).publish_invenio(exp, CREDENTIALS)

        exp = await _stored(db_session)
        assert exp.mdrepo_id == "rec-999"
        assert exp.mdrepo_published is False
        assert result["id"] == "rec-999"
        assert result["upload_state"] == "queued"


class TestInvenioPublishRetryAfterDraftDeleted:
    """Retry after draft deletion in MDRepo creates a fresh draft."""

    @patch("modules.publishing.service.delete_upload_resources")
    @patch("modules.publishing.submission.is_upload_active", return_value=False)
    @patch("modules.publishing.service.submit_upload_job", return_value="attempt-002")
    @patch("clients.mdrepo.MDRepoClient.check_experiment_status", return_value=None)
    @patch("clients.mdrepo.MDRepoClient.create_experiment", return_value={"id": "rec-new"})
    @patch("clients.metadump.MetadumpClient.extract_metadata_bulk", return_value=[])
    async def test_retry_after_draft_deleted_creates_new_draft(
        self,
        mock_meta: Mock,
        mock_create: Mock,
        mock_check_status: Mock,
        mock_submit: Mock,
        mock_active: Mock,
        mock_delete_resources: Mock,
        db_session: AsyncSession,
        tmp_path: Path,
        clients: Clients,
    ) -> None:
        """Test test_retry_after_draft_deleted_creates_new_draft."""
        await _seed_experiment(db_session)
        (tmp_path / "pubsh").mkdir(parents=True, exist_ok=True)

        failed_status = UploadStatus(attempt_id="attempt-001", state="failed", reason="remote")

        with (
            patch("modules.publishing.submission.read_status", return_value=failed_status),
        ):
            exp = await _stored(db_session)
            exp.mdrepo_id = "rec-deleted"
            exp.mdrepo_published = False
            await db_session.commit()

            result = await PublishingService(db_session, clients).publish_invenio(exp, CREDENTIALS)

            exp = await _stored(db_session)
            assert exp.mdrepo_id == "rec-new"
            assert result["id"] == "rec-new"
            mock_create.assert_called_once()
            mock_delete_resources.assert_called_once()

    @patch("modules.publishing.service.delete_upload_resources")
    @patch("modules.publishing.submission.is_upload_active", return_value=False)
    @patch("modules.publishing.service.submit_upload_job", return_value="attempt-002")
    @patch("clients.mdrepo.MDRepoClient.check_experiment_status", return_value=False)
    @patch("clients.mdrepo.MDRepoClient.create_experiment", return_value={"id": "rec-new"})
    @patch("clients.metadump.MetadumpClient.extract_metadata_bulk", return_value=[])
    async def test_retry_when_draft_exists_reuses_draft(
        self,
        mock_meta: Mock,
        mock_create: Mock,
        mock_check_status: Mock,
        mock_submit: Mock,
        mock_active: Mock,
        mock_delete_resources: Mock,
        db_session: AsyncSession,
        tmp_path: Path,
        clients: Clients,
    ) -> None:
        """Test test_retry_when_draft_exists_reuses_draft."""
        await _seed_experiment(db_session)
        (tmp_path / "pubsh").mkdir(parents=True, exist_ok=True)

        failed_status = UploadStatus(attempt_id="attempt-001", state="failed", reason="remote")

        with (
            patch("modules.publishing.submission.read_status", return_value=failed_status),
        ):
            exp = await _stored(db_session)
            exp.mdrepo_id = "rec-existing"
            exp.mdrepo_published = False
            await db_session.commit()

            result = await PublishingService(db_session, clients).publish_invenio(exp, CREDENTIALS)

            exp = await _stored(db_session)
            assert exp.mdrepo_id == "rec-existing"
            assert result["id"] == "rec-existing"
            mock_create.assert_not_called()

    @patch("modules.publishing.submission.is_upload_active", return_value=False)
    @patch("modules.publishing.service.submit_upload_job", return_value="attempt-002")
    @patch("clients.mdrepo.MDRepoClient.create_experiment", return_value={"id": "rec-new"})
    @patch("clients.metadump.MetadumpClient.extract_metadata_bulk", return_value=[])
    async def test_retry_after_completed_status_orphaned(
        self,
        mock_meta: Mock,
        mock_create: Mock,
        mock_submit: Mock,
        mock_active: Mock,
        db_session: AsyncSession,
        tmp_path: Path,
        clients: Clients,
    ) -> None:
        """Test test_retry_after_completed_status_orphaned."""
        await _seed_experiment(db_session)
        (tmp_path / "pubsh").mkdir(parents=True, exist_ok=True)

        completed_status = UploadStatus(attempt_id="attempt-001", state="completed")

        with (
            patch("modules.publishing.submission.read_status", return_value=completed_status),
        ):
            exp = await _stored(db_session)
            exp.mdrepo_id = None
            exp.mdrepo_published = None
            await db_session.commit()

            result = await PublishingService(db_session, clients).publish_invenio(exp, CREDENTIALS)

            exp = await _stored(db_session)
            assert exp.mdrepo_id == "rec-new"
            assert result["id"] == "rec-new"
            mock_create.assert_called_once()


class TestMdpositHandoffSelectedFiles:
    """Handoff contains individual file links and valid metadata YAML."""

    async def test_handoff_includes_metadata_and_files(
        self, db_session: AsyncSession, tmp_path: Path, clients: Clients
    ) -> None:
        """Test test_handoff_includes_metadata_and_files."""
        await _seed_experiment(db_session)
        exp_dir = tmp_path / "pubsh"
        exp_dir.mkdir(parents=True, exist_ok=True)
        (exp_dir / "my_struct.pdb").write_text("ATOM")
        (exp_dir / "my_top.tpr").write_bytes(b"\x00" * 16)
        (exp_dir / "my_traj.xtc").write_bytes(b"\x00" * 16)
        sim_path = _write_gmx_simulation(
            exp_dir,
            files={"run_input": "my_top.tpr", "reference_structure": "my_struct.pdb", "trajectory": "my_traj.xtc"},
        )

        with (
            patch("modules.publishing.mdposit.MDPOSIT_VRE_LITE_URL", ""),
        ):
            exp = await _stored(db_session)
            result = await PublishingService(db_session, clients).publish_mdposit(exp, sim_path)

            assert result["metadata_file"]["path"] == "inputs.yaml"
            assert result["metadata_file"]["url"].startswith("/dash/api/experiments/pubsh/files/")
            roles = {f["role"] for f in result["files"]}
            assert roles == {"structure", "topology", "trajectory"}
            paths = {f["path"] for f in result["files"]}
            assert "my_struct.pdb" in paths
            assert "my_top.tpr" in paths
            assert "my_traj.xtc" in paths

    async def test_metadata_yaml_contains_expected_fields(
        self, db_session: AsyncSession, tmp_path: Path, clients: Clients
    ) -> None:
        """Test test_metadata_yaml_contains_expected_fields."""
        await _seed_experiment(db_session)
        exp_dir = tmp_path / "pubsh"
        exp_dir.mkdir(parents=True, exist_ok=True)
        (exp_dir / "s.pdb").write_text("ATOM")
        (exp_dir / "t.tpr").write_bytes(b"\x00" * 16)
        (exp_dir / "r.xtc").write_bytes(b"\x00" * 16)
        sim_path = _write_gmx_simulation(
            exp_dir, files={"run_input": "t.tpr", "reference_structure": "s.pdb", "trajectory": "r.xtc"}
        )

        with (
            patch("modules.publishing.mdposit.MDPOSIT_VRE_LITE_URL", ""),
        ):
            exp = await _stored(db_session)
            result = await PublishingService(db_session, clients).publish_mdposit(exp, sim_path)

            assert (exp_dir / "inputs.yaml").exists()
            assert result["metadata_file"]["path"] == "inputs.yaml"
            yaml_content = (exp_dir / "inputs.yaml").read_text()
            assert yaml_content.startswith("name:")
            assert "input_structure_filepath: s.pdb" in yaml_content
            assert "input_topology_filepath: t.tpr" in yaml_content
            assert "input_trajectory_filepaths:" in yaml_content
            assert "- r.xtc" in yaml_content
            assert "program: GROMACS" in yaml_content
            assert "type: trajectory" in yaml_content
            assert "method: Classical MD" in yaml_content


class TestMdpositPublishFileValidation:
    """Validate error messages for missing, nonexistent, unsupported files."""

    async def test_missing_role_key(self, db_session: AsyncSession, tmp_path: Path, clients: Clients) -> None:
        """Simulation missing a file role should raise BadRequest."""
        await _seed_experiment(db_session)
        exp_dir = tmp_path / "pubsh"
        exp_dir.mkdir(parents=True, exist_ok=True)
        (exp_dir / "struct.pdb").write_text("ATOM")
        (exp_dir / "traj.xtc").write_bytes(b"\x00" * 16)
        sim_path = _write_gmx_simulation(
            exp_dir, files={"run_input": "topol.tpr", "reference_structure": "struct.pdb", "trajectory": "traj.xtc"}
        )
        # Rewrite without topology role
        sim_file = exp_dir / sim_path
        content = json.loads(sim_file.read_text())
        del content["files"]["run_input"]
        sim_file.write_text(json.dumps(content))

        exp = await _stored(db_session)
        with pytest.raises(BadRequest, match=r"Invalid simulation"):
            await PublishingService(db_session, clients).publish_mdposit(exp, sim_path)

    async def test_nonexistent_selected_file(self, db_session: AsyncSession, tmp_path: Path, clients: Clients) -> None:
        """Simulation pointing to a nonexistent file should raise BadRequest."""
        await _seed_experiment(db_session)
        exp_dir = tmp_path / "pubsh"
        exp_dir.mkdir(parents=True, exist_ok=True)
        (exp_dir / "topol.tpr").write_bytes(b"\x00" * 16)
        (exp_dir / "traj.xtc").write_bytes(b"\x00" * 16)
        sim_path = _write_gmx_simulation(
            exp_dir,
            files={"run_input": "topol.tpr", "reference_structure": "ghost.pdb", "trajectory": "traj.xtc"},
        )

        exp = await _stored(db_session)
        with pytest.raises(BadRequest, match="Missing files"):
            await PublishingService(db_session, clients).publish_mdposit(exp, sim_path)

    async def test_unsupported_extension(self, db_session: AsyncSession, tmp_path: Path, clients: Clients) -> None:
        """File with wrong extension for its role should raise BadRequest."""
        await _seed_experiment(db_session)
        exp_dir = tmp_path / "pubsh"
        exp_dir.mkdir(parents=True, exist_ok=True)
        (exp_dir / "struct.txt").write_text("not a structure")
        (exp_dir / "topol.tpr").write_bytes(b"\x00" * 16)
        (exp_dir / "traj.xtc").write_bytes(b"\x00" * 16)
        sim_path = _write_gmx_simulation(
            exp_dir,
            files={"run_input": "topol.tpr", "reference_structure": "struct.txt", "trajectory": "traj.xtc"},
        )

        exp = await _stored(db_session)
        with pytest.raises(
            BadRequest,
            match=re.escape("The 'Reference structure' file has an unsupported extension '.txt'. Allowed: gro, pdb."),
        ):
            await PublishingService(db_session, clients).publish_mdposit(exp, sim_path)

    async def test_route_returns_400_for_missing_simulation_path(
        self, client: AsyncClient, db_session: AsyncSession, tmp_path: Path
    ) -> None:
        """Route handler should return 400 when simulation_path is missing for mdposit target."""
        await _seed_experiment(db_session)
        (tmp_path / "pubsh").mkdir(parents=True, exist_ok=True)

        resp = await client.post("/dash/api/experiments/pubsh/publish", json={"target": "mdposit"})
        assert resp.status_code == HTTPStatus.BAD_REQUEST

    async def test_unknown_target_returns_400(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        tmp_path: Path,
        clients: Clients,
    ) -> None:
        """Unknown publish target should return 400."""
        await _seed_experiment(db_session)
        (tmp_path / "pubsh").mkdir(parents=True, exist_ok=True)

        resp = await client.post("/dash/api/experiments/pubsh/publish", json={"target": "unknown_target"})
        assert resp.status_code == HTTPStatus.BAD_REQUEST


class TestImportMdpositRepo:
    """Tests for _import_mdposit_repo called via Experiment.from_repo."""

    @patch("clients.mdposit.MDPositClient.download_project")
    @patch("clients.mdposit.MDPositClient.get_project", return_value={"accession": "PRJ1"})
    @patch("clients.mdposit.is_mdposit_url", return_value=True)
    @patch("clients.git.GitClient.clone")
    async def test_from_repo_mdposit_creates_experiment(
        self,
        mock_clone: Mock,
        mock_is_url: Mock,
        mock_get_proj: Mock,
        mock_dl_proj: Mock,
        db_session: AsyncSession,
        tmp_path: Path,
        clients: Clients,
    ) -> None:
        """Test test_from_repo_mdposit_creates_experiment."""
        exp_dir = tmp_path / "mpcr1"
        exp_dir.mkdir(parents=True, exist_ok=True)

        def fake_download(_accession: str, output_dir: Path) -> list[Path]:
            f = output_dir / "sim.gro"
            f.parent.mkdir(parents=True, exist_ok=True)
            f.write_text("fake gro")
            return [f]

        mock_dl_proj.side_effect = fake_download

        with (
            patch(
                "modules.experiments.service.resolve_repo_link", return_value="https://mdposit.mddbr.eu/projects/PRJ1"
            ),
            patch("clients.mdposit.extract_accession", return_value="PRJ1"),
            patch("modules.experiments.service.ExperimentService.prepare_env", return_value="mpcr1"),
        ):
            exp = await ExperimentService(db_session, clients).from_repo(
                name="MDPosit Import",
                repo_link="https://mdposit.mddbr.eu/projects/PRJ1",
                notebooks_repo="https://github.com/t/r.git",
            )
            assert exp is not None
            assert exp.name == "MDPosit Import"
            mock_get_proj.assert_called_once_with("PRJ1")

    @patch("clients.mdposit.extract_accession", return_value="")
    @patch("clients.mdposit.is_mdposit_url", return_value=True)
    @patch("clients.git.GitClient.clone")
    async def test_from_repo_mdposit_missing_accession_raises(
        self,
        mock_clone: Mock,
        mock_is_url: Mock,
        mock_extract: Mock,
        db_session: AsyncSession,
        tmp_path: Path,
        clients: Clients,
    ) -> None:
        """Test test_from_repo_mdposit_missing_accession_raises."""
        (tmp_path / "mpacc1").mkdir(parents=True, exist_ok=True)

        with (
            patch("modules.experiments.service.resolve_repo_link", return_value="https://mdposit.mddbr.eu/"),
            patch("modules.experiments.service.ExperimentService.prepare_env", return_value="mpacc1"),
            pytest.raises(BadRequest, match="Missing MDPosit project accession"),
        ):
            await ExperimentService(db_session, clients).from_repo(
                name="Bad Accession",
                repo_link="https://mdposit.mddbr.eu/",
                notebooks_repo="https://github.com/t/r.git",
            )

    @patch("clients.mdposit.MDPositClient.download_project", side_effect=ValueError("No files found"))
    @patch("clients.mdposit.MDPositClient.get_project", return_value={"accession": "EMPTY"})
    @patch("clients.mdposit.is_mdposit_url", return_value=True)
    @patch("clients.git.GitClient.clone")
    async def test_from_repo_mdposit_no_files_raises(
        self,
        mock_clone: Mock,
        mock_is_url: Mock,
        mock_get_proj: Mock,
        mock_dl_proj: Mock,
        db_session: AsyncSession,
        tmp_path: Path,
        clients: Clients,
    ) -> None:
        """Test test_from_repo_mdposit_no_files_raises."""
        (tmp_path / "mpnf1").mkdir(parents=True, exist_ok=True)

        with (
            patch(
                "modules.experiments.service.resolve_repo_link", return_value="https://mdposit.mddbr.eu/projects/EMPTY"
            ),
            patch("clients.mdposit.extract_accession", return_value="EMPTY"),
            patch("modules.experiments.service.ExperimentService.prepare_env", return_value="mpnf1"),
            pytest.raises(BadRequest, match="No files found"),
        ):
            await ExperimentService(db_session, clients).from_repo(
                name="No Files",
                repo_link="https://mdposit.mddbr.eu/projects/EMPTY",
                notebooks_repo="https://github.com/t/r.git",
            )


class TestFromRepoRouting:
    """from_repo delegates to _import_mdposit_repo or _import_invenio_repo based on URL."""

    @patch("modules.experiments.service.import_invenio_repo")
    @patch("clients.mdposit.is_mdposit_url", return_value=False)
    @patch("clients.git.GitClient.clone")
    async def test_from_repo_invenio_url(
        self,
        mock_clone: Mock,
        mock_is: Mock,
        mock_import: Mock,
        db_session: AsyncSession,
        tmp_path: Path,
        clients: Clients,
    ) -> None:
        """Test test_from_repo_invenio_url."""
        (tmp_path / "inv01").mkdir(parents=True, exist_ok=True)

        with (
            patch("modules.experiments.service.resolve_repo_link", return_value="https://zenodo.org/records/12345"),
            patch("modules.experiments.service.ExperimentService.prepare_env", return_value="inv01"),
        ):
            await ExperimentService(db_session, clients).from_repo(
                name="Invenio Repo",
                repo_link="https://zenodo.org/records/12345",
                notebooks_repo="https://github.com/t/r.git",
            )
            mock_import.assert_called_once()

    @patch("modules.experiments.service.import_mdposit_repo")
    @patch("clients.mdposit.is_mdposit_url", return_value=True)
    @patch("clients.git.GitClient.clone")
    async def test_from_repo_mdposit_url(
        self,
        mock_clone: Mock,
        mock_is: Mock,
        mock_import: Mock,
        db_session: AsyncSession,
        tmp_path: Path,
        clients: Clients,
    ) -> None:
        """Test test_from_repo_mdposit_url."""
        (tmp_path / "mp01").mkdir(parents=True, exist_ok=True)

        with (
            patch("modules.experiments.service.resolve_repo_link", return_value="https://mdposit.mddbr.eu/projects/P1"),
            patch("modules.experiments.service.ExperimentService.prepare_env", return_value="mp01"),
        ):
            await ExperimentService(db_session, clients).from_repo(
                name="MDPosit Repo",
                repo_link="https://mdposit.mddbr.eu/projects/P1",
                notebooks_repo="https://github.com/t/r.git",
            )
            mock_import.assert_called_once()
