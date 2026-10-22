"""Unit tests for MDPosit-aware publish routing and from_repo logic."""

import json
import re
from collections.abc import Iterator
from http import HTTPStatus
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

import pytest
from clients import Clients
from core.errors import ApiError, BadRequest
from httpx import AsyncClient
from modules.experiments.service import ExperimentService
from modules.mdrepo.tokens import MDRepoCredentials
from modules.models import Experiment
from modules.publishing.service import PublishingService
from modules.publishing.status import UploadStatus
from modules.publishing.submission import SubmissionError
from sqlalchemy.ext.asyncio import AsyncSession
from tests.support import SeedExperiment, write_simulation

EXP_ID = "pubsh"
SIM_PATH = "sim.simulation.json"
PUBLISH_FILES = {"run_input": "topol.tpr", "reference_structure": "struct.pdb", "trajectory": "traj.xtc"}
CREDENTIALS = MDRepoCredentials(access_token="valid-token", refresh_token="", expires_at="0")


@pytest.fixture(autouse=True)
def _mdposit_configured() -> Iterator[None]:
    """Ensure MDPOSIT_URL is set for all tests in this module unless overridden."""
    with patch("modules.publishing.mdposit.MDPOSIT_URL", "https://mdposit.example.com"):
        yield


async def _stored(db_session: AsyncSession, exp_id: str = EXP_ID) -> Experiment:
    db_session.expunge_all()
    experiment = await db_session.get(Experiment, exp_id)
    assert experiment is not None
    return experiment


@pytest.fixture
def upload() -> Iterator[SimpleNamespace]:
    """Patch MDRepo, MetaDump, and the upload Job for a first publish; tests adjust the mocks."""
    with (
        patch("modules.publishing.submission.is_upload_active", return_value=False) as active,
        patch("modules.publishing.service.submit_upload_job", return_value="attempt-001") as submit,
        patch("modules.publishing.submission.read_status", return_value=None) as read_status,
        patch("clients.mdrepo.MDRepoClient.create_experiment", return_value={"id": "rec-001"}) as create,
        patch("clients.mdrepo.MDRepoClient.check_experiment_status", return_value=None) as check,
        patch("clients.metadump.MetadumpClient.extract_metadata_bulk", return_value=[]) as metadata,
        patch("modules.publishing.service.delete_upload_resources") as delete_resources,
    ):
        yield SimpleNamespace(
            active=active,
            submit=submit,
            read_status=read_status,
            create=create,
            check=check,
            metadata=metadata,
            delete_resources=delete_resources,
        )


@pytest.fixture
def clone() -> Iterator[Mock]:
    with patch("clients.git.GitClient.clone") as clone:
        yield clone


class TestDefaultPublishTargetInvenio:
    """Default target=invenio requires MDRepo authentication."""

    async def test_publish_default_target_requires_mdrepo_token(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        tmp_path: Path,
        seed_experiment: SeedExperiment,
    ) -> None:
        await seed_experiment(EXP_ID, name="Publish Test")

        resp = await client.post("/dash/api/experiments/pubsh/publish")
        assert resp.status_code == HTTPStatus.UNAUTHORIZED
        assert "MDRepo" in resp.json()["detail"]

    async def test_publish_explicit_invenio_also_requires_token(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        tmp_path: Path,
        clients: Clients,
        seed_experiment: SeedExperiment,
    ) -> None:
        await seed_experiment(EXP_ID, name="Publish Test")

        resp = await client.post("/dash/api/experiments/pubsh/publish", json={"target": "invenio"})
        assert resp.status_code == HTTPStatus.UNAUTHORIZED

    async def test_publish_invenio_with_token_succeeds(
        self,
        db_session: AsyncSession,
        tmp_path: Path,
        clients: Clients,
        seed_experiment: SeedExperiment,
        upload: SimpleNamespace,
    ) -> None:
        await seed_experiment(EXP_ID, name="Publish Test")

        exp = await _stored(db_session)
        result = await PublishingService(db_session, clients).publish_invenio(exp, CREDENTIALS)

        assert result["id"] == "rec-001"
        assert result["upload_state"] == "queued"
        upload.create.assert_called_once()


class TestMdpositPublishNoOAuth:
    """MDPosit publish does not require MDRepo OAuth token."""

    async def test_mdposit_publish_does_not_require_mdrepo_token(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        tmp_path: Path,
        seed_experiment: SeedExperiment,
    ) -> None:
        _, exp_dir = await seed_experiment(EXP_ID, name="Publish Test")
        (exp_dir / "struct.pdb").write_text("ATOM data")
        (exp_dir / "topol.tpr").write_bytes(b"\x00" * 16)
        (exp_dir / "traj.xtc").write_bytes(b"\x00" * 16)
        sim_path = write_simulation(
            exp_dir,
            SIM_PATH,
            {"run_input": "topol.tpr", "reference_structure": "struct.pdb", "trajectory": "traj.xtc"},
            name="sim",
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
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        tmp_path: Path,
        seed_experiment: SeedExperiment,
    ) -> None:
        _, exp_dir = await seed_experiment(EXP_ID, name="Publish Test")
        (exp_dir / "struct.pdb").write_text("ATOM data")
        (exp_dir / "topol.tpr").write_bytes(b"\x00" * 16)
        (exp_dir / "traj.xtc").write_bytes(b"\x00" * 16)
        sim_path = write_simulation(exp_dir, SIM_PATH, PUBLISH_FILES, name="sim")

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
        self,
        db_session: AsyncSession,
        tmp_path: Path,
        clients: Clients,
        seed_experiment: SeedExperiment,
    ) -> None:
        _, exp_dir = await seed_experiment(EXP_ID, name="Publish Test")
        (exp_dir / "struct.gro").write_text("gro data")
        (exp_dir / "topol.tpr").write_bytes(b"\x00" * 16)
        (exp_dir / "traj.xtc").write_bytes(b"\x00" * 16)
        sim_path = write_simulation(
            exp_dir,
            SIM_PATH,
            {"run_input": "topol.tpr", "reference_structure": "struct.gro", "trajectory": "traj.xtc"},
            name="sim",
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
        seed_experiment: SeedExperiment,
    ) -> None:
        _, exp_dir = await seed_experiment(EXP_ID, name="Publish Test")
        (exp_dir / "struct.pdb").write_text("ATOM")
        (exp_dir / "topol.tpr").write_bytes(b"\x00" * 16)
        (exp_dir / "traj.xtc").write_bytes(b"\x00" * 16)
        sim_path = write_simulation(exp_dir, SIM_PATH, PUBLISH_FILES, name="sim")

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

    async def test_invenio_publish_sets_mdrepo_fields(
        self,
        db_session: AsyncSession,
        tmp_path: Path,
        clients: Clients,
        seed_experiment: SeedExperiment,
        upload: SimpleNamespace,
    ) -> None:
        upload.create.return_value = {"id": "rec-999"}
        upload.submit.return_value = "attempt-999"
        await seed_experiment(EXP_ID, name="Publish Test")

        exp = await _stored(db_session)
        result = await PublishingService(db_session, clients).publish_invenio(exp, CREDENTIALS)

        exp = await _stored(db_session)
        assert exp.mdrepo_id == "rec-999"
        assert exp.mdrepo_published is False
        assert result["id"] == "rec-999"
        assert result["upload_state"] == "queued"


class TestInvenioPublishUpstreamFailures:
    """MDRepo draft and upload-Job failures surface as upstream-unavailable, never a generic 500."""

    async def test_draft_creation_failure(
        self,
        db_session: AsyncSession,
        tmp_path: Path,
        clients: Clients,
        seed_experiment: SeedExperiment,
        upload: SimpleNamespace,
    ) -> None:
        upload.create.side_effect = ValueError("Failed to create experiment: 500")
        await seed_experiment(EXP_ID, name="Publish Test")

        with pytest.raises(ApiError) as exc_info:
            await PublishingService(db_session, clients).publish_invenio(await _stored(db_session), CREDENTIALS)

        assert exc_info.value.problem_type == "urn:mddash:upstream-unavailable"
        assert exc_info.value.problem_solution is not None

    async def test_upload_job_submission_failure(
        self,
        db_session: AsyncSession,
        tmp_path: Path,
        clients: Clients,
        seed_experiment: SeedExperiment,
        upload: SimpleNamespace,
    ) -> None:
        upload.create.return_value = {"id": "rec-1"}
        upload.submit.side_effect = SubmissionError("pod not admitted")
        await seed_experiment(EXP_ID, name="Publish Test")

        with pytest.raises(ApiError) as exc_info:
            await PublishingService(db_session, clients).publish_invenio(await _stored(db_session), CREDENTIALS)

        assert exc_info.value.problem_type == "urn:mddash:upstream-unavailable"
        assert "upload" in exc_info.value.detail


class TestInvenioPublishRetryAfterDraftDeleted:
    """Retry after draft deletion in MDRepo creates a fresh draft."""

    async def test_retry_after_draft_deleted_creates_new_draft(
        self,
        db_session: AsyncSession,
        tmp_path: Path,
        clients: Clients,
        seed_experiment: SeedExperiment,
        upload: SimpleNamespace,
    ) -> None:
        upload.create.return_value = {"id": "rec-new"}
        upload.submit.return_value = "attempt-002"
        await seed_experiment(EXP_ID, name="Publish Test")

        failed_status = UploadStatus(attempt_id="attempt-001", state="failed", reason="remote")

        upload.read_status.return_value = failed_status

        exp = await _stored(db_session)
        exp.mdrepo_id = "rec-deleted"
        exp.mdrepo_published = False
        await db_session.commit()

        result = await PublishingService(db_session, clients).publish_invenio(exp, CREDENTIALS)

        exp = await _stored(db_session)
        assert exp.mdrepo_id == "rec-new"
        assert result["id"] == "rec-new"
        upload.create.assert_called_once()
        upload.delete_resources.assert_called_once()

    async def test_retry_when_draft_exists_reuses_draft(
        self,
        db_session: AsyncSession,
        tmp_path: Path,
        clients: Clients,
        seed_experiment: SeedExperiment,
        upload: SimpleNamespace,
    ) -> None:
        upload.create.return_value = {"id": "rec-new"}
        upload.check.return_value = False
        upload.submit.return_value = "attempt-002"
        await seed_experiment(EXP_ID, name="Publish Test")

        failed_status = UploadStatus(attempt_id="attempt-001", state="failed", reason="remote")

        upload.read_status.return_value = failed_status

        exp = await _stored(db_session)
        exp.mdrepo_id = "rec-existing"
        exp.mdrepo_published = False
        await db_session.commit()

        result = await PublishingService(db_session, clients).publish_invenio(exp, CREDENTIALS)

        exp = await _stored(db_session)
        assert exp.mdrepo_id == "rec-existing"
        assert result["id"] == "rec-existing"
        upload.create.assert_not_called()

    async def test_retry_after_completed_status_orphaned(
        self,
        db_session: AsyncSession,
        tmp_path: Path,
        clients: Clients,
        seed_experiment: SeedExperiment,
        upload: SimpleNamespace,
    ) -> None:
        upload.create.return_value = {"id": "rec-new"}
        upload.submit.return_value = "attempt-002"
        await seed_experiment(EXP_ID, name="Publish Test")

        completed_status = UploadStatus(attempt_id="attempt-001", state="completed")

        upload.read_status.return_value = completed_status

        exp = await _stored(db_session)
        exp.mdrepo_id = None
        exp.mdrepo_published = None
        await db_session.commit()

        result = await PublishingService(db_session, clients).publish_invenio(exp, CREDENTIALS)

        exp = await _stored(db_session)
        assert exp.mdrepo_id == "rec-new"
        assert result["id"] == "rec-new"
        upload.create.assert_called_once()


class TestMdpositHandoffSelectedFiles:
    """Handoff contains individual file links and valid metadata YAML."""

    async def test_handoff_includes_metadata_and_files(
        self,
        db_session: AsyncSession,
        tmp_path: Path,
        clients: Clients,
        seed_experiment: SeedExperiment,
    ) -> None:
        _, exp_dir = await seed_experiment(EXP_ID, name="Publish Test")
        (exp_dir / "my_struct.pdb").write_text("ATOM")
        (exp_dir / "my_top.tpr").write_bytes(b"\x00" * 16)
        (exp_dir / "my_traj.xtc").write_bytes(b"\x00" * 16)
        sim_path = write_simulation(
            exp_dir,
            SIM_PATH,
            {"run_input": "my_top.tpr", "reference_structure": "my_struct.pdb", "trajectory": "my_traj.xtc"},
            name="sim",
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
        self,
        db_session: AsyncSession,
        tmp_path: Path,
        clients: Clients,
        seed_experiment: SeedExperiment,
    ) -> None:
        _, exp_dir = await seed_experiment(EXP_ID, name="Publish Test")
        (exp_dir / "s.pdb").write_text("ATOM")
        (exp_dir / "t.tpr").write_bytes(b"\x00" * 16)
        (exp_dir / "r.xtc").write_bytes(b"\x00" * 16)
        sim_path = write_simulation(
            exp_dir, SIM_PATH, {"run_input": "t.tpr", "reference_structure": "s.pdb", "trajectory": "r.xtc"}, name="sim"
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

    async def test_missing_role_key(
        self, db_session: AsyncSession, tmp_path: Path, clients: Clients, seed_experiment: SeedExperiment
    ) -> None:
        """Simulation missing a file role should raise BadRequest."""
        _, exp_dir = await seed_experiment(EXP_ID, name="Publish Test")
        (exp_dir / "struct.pdb").write_text("ATOM")
        (exp_dir / "traj.xtc").write_bytes(b"\x00" * 16)
        sim_path = write_simulation(
            exp_dir,
            SIM_PATH,
            {"run_input": "topol.tpr", "reference_structure": "struct.pdb", "trajectory": "traj.xtc"},
            name="sim",
        )
        # Rewrite without topology role
        sim_file = exp_dir / sim_path
        content = json.loads(sim_file.read_text())
        del content["files"]["run_input"]
        sim_file.write_text(json.dumps(content))

        exp = await _stored(db_session)
        with pytest.raises(BadRequest, match=r"Invalid simulation"):
            await PublishingService(db_session, clients).publish_mdposit(exp, sim_path)

    async def test_nonexistent_selected_file(
        self, db_session: AsyncSession, tmp_path: Path, clients: Clients, seed_experiment: SeedExperiment
    ) -> None:
        """Simulation pointing to a nonexistent file should raise BadRequest."""
        _, exp_dir = await seed_experiment(EXP_ID, name="Publish Test")
        (exp_dir / "topol.tpr").write_bytes(b"\x00" * 16)
        (exp_dir / "traj.xtc").write_bytes(b"\x00" * 16)
        sim_path = write_simulation(
            exp_dir,
            SIM_PATH,
            {"run_input": "topol.tpr", "reference_structure": "ghost.pdb", "trajectory": "traj.xtc"},
            name="sim",
        )

        exp = await _stored(db_session)
        with pytest.raises(BadRequest, match="Missing files"):
            await PublishingService(db_session, clients).publish_mdposit(exp, sim_path)

    async def test_unsupported_extension(
        self, db_session: AsyncSession, tmp_path: Path, clients: Clients, seed_experiment: SeedExperiment
    ) -> None:
        """File with wrong extension for its role should raise BadRequest."""
        _, exp_dir = await seed_experiment(EXP_ID, name="Publish Test")
        (exp_dir / "struct.txt").write_text("not a structure")
        (exp_dir / "topol.tpr").write_bytes(b"\x00" * 16)
        (exp_dir / "traj.xtc").write_bytes(b"\x00" * 16)
        sim_path = write_simulation(
            exp_dir,
            SIM_PATH,
            {"run_input": "topol.tpr", "reference_structure": "struct.txt", "trajectory": "traj.xtc"},
            name="sim",
        )

        exp = await _stored(db_session)
        with pytest.raises(
            BadRequest,
            match=re.escape("The 'Reference structure' file has an unsupported extension '.txt'. Allowed: gro, pdb."),
        ):
            await PublishingService(db_session, clients).publish_mdposit(exp, sim_path)

    async def test_route_returns_400_for_missing_simulation_path(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        tmp_path: Path,
        seed_experiment: SeedExperiment,
    ) -> None:
        """Route handler should return 400 when simulation_path is missing for mdposit target."""
        await seed_experiment(EXP_ID, name="Publish Test")

        resp = await client.post("/dash/api/experiments/pubsh/publish", json={"target": "mdposit"})
        assert resp.status_code == HTTPStatus.BAD_REQUEST

    async def test_unknown_target_returns_400(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        tmp_path: Path,
        clients: Clients,
        seed_experiment: SeedExperiment,
    ) -> None:
        """Unknown publish target should return 400."""
        await seed_experiment(EXP_ID, name="Publish Test")

        resp = await client.post("/dash/api/experiments/pubsh/publish", json={"target": "unknown_target"})
        assert resp.status_code == HTTPStatus.BAD_REQUEST


class TestImportMdpositRepo:
    """Tests for _import_mdposit_repo called via Experiment.from_repo."""

    @patch("clients.mdposit.MDPositClient.download_project")
    @patch("clients.mdposit.MDPositClient.get_project", return_value={"accession": "PRJ1"})
    @patch("clients.mdposit.is_mdposit_url", return_value=True)
    async def test_from_repo_mdposit_creates_experiment(
        self,
        mock_is_url: Mock,
        mock_get_proj: Mock,
        mock_dl_proj: Mock,
        db_session: AsyncSession,
        tmp_path: Path,
        clients: Clients,
        clone: Mock,
    ) -> None:
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
    async def test_from_repo_mdposit_missing_accession_raises(
        self,
        mock_is_url: Mock,
        mock_extract: Mock,
        db_session: AsyncSession,
        tmp_path: Path,
        clients: Clients,
        clone: Mock,
    ) -> None:
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
    async def test_from_repo_mdposit_no_files_raises(
        self,
        mock_is_url: Mock,
        mock_get_proj: Mock,
        mock_dl_proj: Mock,
        db_session: AsyncSession,
        tmp_path: Path,
        clients: Clients,
        clone: Mock,
    ) -> None:
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
    async def test_from_repo_invenio_url(
        self,
        mock_is: Mock,
        mock_import: Mock,
        db_session: AsyncSession,
        tmp_path: Path,
        clients: Clients,
        clone: Mock,
    ) -> None:
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
    async def test_from_repo_mdposit_url(
        self,
        mock_is: Mock,
        mock_import: Mock,
        db_session: AsyncSession,
        tmp_path: Path,
        clients: Clients,
        clone: Mock,
    ) -> None:
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
