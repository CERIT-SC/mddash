"""Unit tests for MDPosit-aware publish routing and from_repo logic."""

import json
from collections.abc import Generator
from http import HTTPStatus
from pathlib import Path
from unittest.mock import Mock, patch

import pytest
from enums import Engine
from errors import register_error_handlers
from extensions import db, ma
from flask import Flask
from flask.testing import FlaskClient
from manifest_schema import schema_url
from models import Experiment, Notebook
from routes import experiments_bp, mdrepo_bp
from upload.status import UploadStatus
from werkzeug.exceptions import BadRequest, InternalServerError

GMX_SCHEMA_URL = schema_url(Engine.GMX)


@pytest.fixture
def app(tmp_path: Path) -> Generator[Flask, None, None]:
    """
    Create a Flask app with in-memory SQLite for model-level publish tests.

    Yields:
        Configured Flask application with database tables created.
    """
    test_app = Flask(__name__)
    test_app.config["TESTING"] = True
    test_app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///:memory:"
    test_app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
    test_app.config["SECRET_KEY"] = "test-secret-key"

    db.init_app(test_app)
    ma.init_app(test_app)

    with patch.dict("config.__dict__", {"DATA_DIR": tmp_path}), patch("models.simulation.DATA_DIR", tmp_path):
        test_app.register_blueprint(experiments_bp)
        test_app.register_blueprint(mdrepo_bp)
        register_error_handlers(test_app)

        with test_app.app_context():
            db.create_all()
            yield test_app
            db.drop_all()


@pytest.fixture
def _mdposit_configured() -> Generator[None, None, None]:
    """Ensure MDPOSIT_URL is set for all tests in this module unless overridden."""
    with patch("models.experiment.MDPOSIT_URL", "https://mdposit.example.com"):
        yield


pytestmark = pytest.mark.usefixtures("_mdposit_configured")


@pytest.fixture
def client(app: Flask) -> FlaskClient:
    """
    Flask test client.

    Returns:
        Flask test client instance.
    """
    return app.test_client()


def _seed_experiment(app: Flask, exp_id: str = "pubsh", name: str = "Publish Test") -> str:
    """
    Seed a minimal experiment with notebook into the DB.

    Returns:
        The experiment ID.
    """
    with app.app_context():
        exp = Experiment(id=exp_id, name=name, source_message="test", notebooks_repo="https://github.com/t/r.git")
        db.session.add(exp)
        db.session.flush()
        nb = Notebook(experiment_id=exp_id)
        db.session.add(nb)
        db.session.commit()
        return exp_id


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

    def test_publish_default_target_requires_mdrepo_token(self, app: Flask, tmp_path: Path) -> None:
        """Test test_publish_default_target_requires_mdrepo_token."""
        _seed_experiment(app)
        (tmp_path / "pubsh").mkdir(parents=True, exist_ok=True)

        with app.test_client() as c:
            resp = c.post("/dash/api/experiments/pubsh/publish", content_type="application/json")
            assert resp.status_code == HTTPStatus.UNAUTHORIZED
            assert "MDRepo" in resp.get_json()["detail"]

    def test_publish_explicit_invenio_also_requires_token(self, app: Flask, tmp_path: Path) -> None:
        """Test test_publish_explicit_invenio_also_requires_token."""
        _seed_experiment(app)
        (tmp_path / "pubsh").mkdir(parents=True, exist_ok=True)

        with app.test_client() as c:
            resp = c.post(
                "/dash/api/experiments/pubsh/publish",
                json={"target": "invenio"},
                content_type="application/json",
            )
            assert resp.status_code == HTTPStatus.UNAUTHORIZED

    @patch("models.experiment.is_upload_active", return_value=False)
    @patch("models.experiment.submit_upload_job", return_value="attempt-001")
    @patch("models.experiment.read_status", return_value=None)
    @patch("models.experiment.mdrepo.create_experiment", return_value={"id": "rec-001"})
    @patch("models.experiment.metadump.extract_metadata_bulk", return_value=[])
    def test_publish_invenio_with_token_succeeds(
        self,
        mock_meta: Mock,
        mock_create: Mock,
        mock_read_status: Mock,
        mock_submit: Mock,
        mock_active: Mock,
        app: Flask,
        tmp_path: Path,
    ) -> None:
        """Test test_publish_invenio_with_token_succeeds."""
        _seed_experiment(app)
        (tmp_path / "pubsh").mkdir(parents=True, exist_ok=True)

        with (
            patch("models.experiment.DATA_DIR", tmp_path),
            patch("models.simulation.DATA_DIR", tmp_path),
            app.app_context(),
        ):
            exp = Experiment.query.get("pubsh")
            token_manager = Mock()
            token_manager.get_valid_token.return_value = "valid-token"
            with patch("models.experiment.MDRepoTokenManager", return_value=token_manager):
                result = exp.publish(target="invenio", community="ceitec")

            assert result["id"] == "rec-001"
            assert result["upload_state"] == "queued"
            mock_create.assert_called_once()


class TestMdpositPublishNoOAuth:
    """MDPosit publish does not require MDRepo OAuth token."""

    def test_mdposit_publish_does_not_require_mdrepo_token(self, app: Flask, tmp_path: Path) -> None:
        """Test test_mdposit_publish_does_not_require_mdrepo_token."""
        _seed_experiment(app)
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
            patch("models.experiment.DATA_DIR", tmp_path),
            patch("models.simulation.DATA_DIR", tmp_path),
            patch("models.experiment.MDPOSIT_VRE_LITE_URL", "https://mdposit.example.com/vre_lite/"),
            app.test_client() as c,
        ):
            resp = c.post(
                "/dash/api/experiments/pubsh/publish",
                json={"target": "mdposit", "simulation_path": sim_path},
                content_type="application/json",
            )
            assert resp.status_code == HTTPStatus.CREATED
            data = resp.get_json()
            assert "metadata_file" in data
            assert "files" in data
            assert len(data["files"]) == len({"structure", "topology", "trajectory"})
            assert "vre_lite_url" in data

    def test_mdposit_publish_rejected_when_not_configured(self, app: Flask, tmp_path: Path) -> None:
        """Test test_mdposit_publish_rejected_when_not_configured."""
        _seed_experiment(app)
        exp_dir = tmp_path / "pubsh"
        exp_dir.mkdir(parents=True, exist_ok=True)
        (exp_dir / "struct.pdb").write_text("ATOM data")
        (exp_dir / "topol.tpr").write_bytes(b"\x00" * 16)
        (exp_dir / "traj.xtc").write_bytes(b"\x00" * 16)
        sim_path = _write_gmx_simulation(exp_dir)

        with (
            patch("models.experiment.DATA_DIR", tmp_path),
            patch("models.simulation.DATA_DIR", tmp_path),
            patch("models.experiment.MDPOSIT_URL", ""),
            app.test_client() as c,
        ):
            resp = c.post(
                "/dash/api/experiments/pubsh/publish",
                json={"target": "mdposit", "simulation_path": sim_path},
                content_type="application/json",
            )
            assert resp.status_code == HTTPStatus.BAD_REQUEST


class TestMdpositPublishNoDbMutation:
    """MDPosit handoff is stateless — must not change MDRepo columns."""

    def test_mdposit_publish_leaves_mdrepo_fields_null(self, app: Flask, tmp_path: Path) -> None:
        """Test test_mdposit_publish_leaves_mdrepo_fields_null."""
        _seed_experiment(app)
        exp_dir = tmp_path / "pubsh"
        exp_dir.mkdir(parents=True, exist_ok=True)
        (exp_dir / "struct.gro").write_text("gro data")
        (exp_dir / "topol.tpr").write_bytes(b"\x00" * 16)
        (exp_dir / "traj.xtc").write_bytes(b"\x00" * 16)
        sim_path = _write_gmx_simulation(
            exp_dir, files={"run_input": "topol.tpr", "reference_structure": "struct.gro", "trajectory": "traj.xtc"}
        )

        with (
            patch("models.experiment.DATA_DIR", tmp_path),
            patch("models.simulation.DATA_DIR", tmp_path),
            patch("models.experiment.MDPOSIT_VRE_LITE_URL", "https://mdposit.example.com/vre_lite/"),
            app.app_context(),
        ):
            exp = Experiment.query.get("pubsh")
            assert exp.mdrepo_id is None
            assert exp.mdrepo_published is None

            result = exp.publish(target="mdposit", simulation_path=sim_path)

            db.session.refresh(exp)
            assert exp.mdrepo_id is None
            assert exp.mdrepo_published is None
            assert "metadata_file" in result
            assert result["metadata_file"]["path"] == "inputs.yaml"

    def test_mdposit_publish_does_not_overwrite_existing_mdrepo_fields(self, app: Flask, tmp_path: Path) -> None:
        """Test test_mdposit_publish_does_not_overwrite_existing_mdrepo_fields."""
        _seed_experiment(app)
        exp_dir = tmp_path / "pubsh"
        exp_dir.mkdir(parents=True, exist_ok=True)
        (exp_dir / "struct.pdb").write_text("ATOM")
        (exp_dir / "topol.tpr").write_bytes(b"\x00" * 16)
        (exp_dir / "traj.xtc").write_bytes(b"\x00" * 16)
        sim_path = _write_gmx_simulation(exp_dir)

        with (
            patch("models.experiment.DATA_DIR", tmp_path),
            patch("models.simulation.DATA_DIR", tmp_path),
            patch("models.experiment.MDPOSIT_VRE_LITE_URL", ""),
            app.app_context(),
        ):
            exp = Experiment.query.get("pubsh")
            exp.mdrepo_id = "existing-mdrepo-id"
            exp.mdrepo_published = True
            db.session.commit()

            exp.publish(target="mdposit", simulation_path=sim_path)

            db.session.refresh(exp)
            assert exp.mdrepo_id == "existing-mdrepo-id"
            assert exp.mdrepo_published is True


class TestInvenioPublishUnchanged:
    """Invenio publish still sets mdrepo_id and mdrepo_published=False."""

    @patch("models.experiment.is_upload_active", return_value=False)
    @patch("models.experiment.submit_upload_job", return_value="attempt-999")
    @patch("models.experiment.read_status", return_value=None)
    @patch("models.experiment.mdrepo.create_experiment", return_value={"id": "rec-999"})
    @patch("models.experiment.metadump.extract_metadata_bulk", return_value=[])
    def test_invenio_publish_sets_mdrepo_fields(
        self,
        mock_meta: Mock,
        mock_create: Mock,
        mock_read_status: Mock,
        mock_submit: Mock,
        mock_active: Mock,
        app: Flask,
        tmp_path: Path,
    ) -> None:
        """Test test_invenio_publish_sets_mdrepo_fields."""
        _seed_experiment(app)
        (tmp_path / "pubsh").mkdir(parents=True, exist_ok=True)

        with (
            patch("models.experiment.DATA_DIR", tmp_path),
            patch("models.simulation.DATA_DIR", tmp_path),
            app.app_context(),
        ):
            exp = Experiment.query.get("pubsh")
            token_manager = Mock()
            token_manager.get_valid_token.return_value = "tok"

            with patch("models.experiment.MDRepoTokenManager", return_value=token_manager):
                result = exp.publish(target="invenio", community="ceitec")

            db.session.refresh(exp)
            assert exp.mdrepo_id == "rec-999"
            assert exp.mdrepo_published is False
            assert result["id"] == "rec-999"
            assert result["upload_state"] == "queued"

    @patch("models.experiment.mdrepo.create_experiment", return_value={"id": "rec-999"})
    @patch("models.experiment.metadump.extract_metadata_bulk", return_value=[])
    def test_invenio_publish_raises_without_token(
        self,
        mock_meta: Mock,
        mock_create: Mock,
        app: Flask,
        tmp_path: Path,
    ) -> None:
        """Test test_invenio_publish_raises_without_token."""
        _seed_experiment(app)
        (tmp_path / "pubsh").mkdir(parents=True, exist_ok=True)

        with (
            patch("models.experiment.DATA_DIR", tmp_path),
            patch("models.simulation.DATA_DIR", tmp_path),
            app.app_context(),
        ):
            exp = Experiment.query.get("pubsh")
            token_manager = Mock()
            token_manager.get_valid_token.return_value = None

            with (
                patch("models.experiment.MDRepoTokenManager", return_value=token_manager),
                pytest.raises(InternalServerError, match="No valid MDRepo access token"),
            ):
                exp.publish(target="invenio")


class TestInvenioPublishRetryAfterDraftDeleted:
    """Retry after draft deletion in MDRepo creates a fresh draft."""

    @patch("models.experiment.delete_upload_resources")
    @patch("models.experiment.is_upload_active", return_value=False)
    @patch("models.experiment.submit_upload_job", return_value="attempt-002")
    @patch("models.experiment.mdrepo.check_experiment_status", return_value=None)
    @patch("models.experiment.mdrepo.create_experiment", return_value={"id": "rec-new"})
    @patch("models.experiment.metadump.extract_metadata_bulk", return_value=[])
    def test_retry_after_draft_deleted_creates_new_draft(
        self,
        mock_meta: Mock,
        mock_create: Mock,
        mock_check_status: Mock,
        mock_submit: Mock,
        mock_active: Mock,
        mock_delete_resources: Mock,
        app: Flask,
        tmp_path: Path,
    ) -> None:
        """Test test_retry_after_draft_deleted_creates_new_draft."""
        _seed_experiment(app)
        (tmp_path / "pubsh").mkdir(parents=True, exist_ok=True)

        failed_status = UploadStatus(attempt_id="attempt-001", state="failed", reason="remote")

        with (
            patch("models.experiment.DATA_DIR", tmp_path),
            patch("models.simulation.DATA_DIR", tmp_path),
            patch("models.experiment.read_status", return_value=failed_status),
            app.app_context(),
        ):
            exp = Experiment.query.get("pubsh")
            exp.mdrepo_id = "rec-deleted"
            exp.mdrepo_published = False
            db.session.commit()

            token_manager = Mock()
            token_manager.get_valid_token.return_value = "valid-token"
            with patch("models.experiment.MDRepoTokenManager", return_value=token_manager):
                result = exp.publish(target="invenio", community="ceitec")

            db.session.refresh(exp)
            assert exp.mdrepo_id == "rec-new"
            assert result["id"] == "rec-new"
            mock_create.assert_called_once()
            mock_delete_resources.assert_called_once()

    @patch("models.experiment.delete_upload_resources")
    @patch("models.experiment.is_upload_active", return_value=False)
    @patch("models.experiment.submit_upload_job", return_value="attempt-002")
    @patch("models.experiment.mdrepo.check_experiment_status", return_value=False)
    @patch("models.experiment.mdrepo.create_experiment", return_value={"id": "rec-new"})
    @patch("models.experiment.metadump.extract_metadata_bulk", return_value=[])
    def test_retry_when_draft_exists_reuses_draft(
        self,
        mock_meta: Mock,
        mock_create: Mock,
        mock_check_status: Mock,
        mock_submit: Mock,
        mock_active: Mock,
        mock_delete_resources: Mock,
        app: Flask,
        tmp_path: Path,
    ) -> None:
        """Test test_retry_when_draft_exists_reuses_draft."""
        _seed_experiment(app)
        (tmp_path / "pubsh").mkdir(parents=True, exist_ok=True)

        failed_status = UploadStatus(attempt_id="attempt-001", state="failed", reason="remote")

        with (
            patch("models.experiment.DATA_DIR", tmp_path),
            patch("models.simulation.DATA_DIR", tmp_path),
            patch("models.experiment.read_status", return_value=failed_status),
            app.app_context(),
        ):
            exp = Experiment.query.get("pubsh")
            exp.mdrepo_id = "rec-existing"
            exp.mdrepo_published = False
            db.session.commit()

            token_manager = Mock()
            token_manager.get_valid_token.return_value = "valid-token"
            with patch("models.experiment.MDRepoTokenManager", return_value=token_manager):
                result = exp.publish(target="invenio", community="ceitec")

            db.session.refresh(exp)
            assert exp.mdrepo_id == "rec-existing"
            assert result["id"] == "rec-existing"
            mock_create.assert_not_called()

    @patch("models.experiment.is_upload_active", return_value=False)
    @patch("models.experiment.submit_upload_job", return_value="attempt-002")
    @patch("models.experiment.mdrepo.create_experiment", return_value={"id": "rec-new"})
    @patch("models.experiment.metadump.extract_metadata_bulk", return_value=[])
    def test_retry_after_completed_status_orphaned(
        self,
        mock_meta: Mock,
        mock_create: Mock,
        mock_submit: Mock,
        mock_active: Mock,
        app: Flask,
        tmp_path: Path,
    ) -> None:
        """Test test_retry_after_completed_status_orphaned."""
        _seed_experiment(app)
        (tmp_path / "pubsh").mkdir(parents=True, exist_ok=True)

        completed_status = UploadStatus(attempt_id="attempt-001", state="completed")

        with (
            patch("models.experiment.DATA_DIR", tmp_path),
            patch("models.simulation.DATA_DIR", tmp_path),
            patch("models.experiment.read_status", return_value=completed_status),
            app.app_context(),
        ):
            exp = Experiment.query.get("pubsh")
            exp.mdrepo_id = None
            exp.mdrepo_published = None
            db.session.commit()

            token_manager = Mock()
            token_manager.get_valid_token.return_value = "valid-token"
            with patch("models.experiment.MDRepoTokenManager", return_value=token_manager):
                result = exp.publish(target="invenio", community="ceitec")

            db.session.refresh(exp)
            assert exp.mdrepo_id == "rec-new"
            assert result["id"] == "rec-new"
            mock_create.assert_called_once()


class TestMdpositHandoffSelectedFiles:
    """Handoff contains individual file links and valid metadata YAML."""

    def test_handoff_includes_metadata_and_files(self, app: Flask, tmp_path: Path) -> None:
        """Test test_handoff_includes_metadata_and_files."""
        _seed_experiment(app)
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
            patch("models.experiment.DATA_DIR", tmp_path),
            patch("models.simulation.DATA_DIR", tmp_path),
            patch("models.experiment.MDPOSIT_VRE_LITE_URL", ""),
            app.app_context(),
        ):
            exp = Experiment.query.get("pubsh")
            result = exp.publish(target="mdposit", simulation_path=sim_path)

            assert result["metadata_file"]["path"] == "inputs.yaml"
            assert result["metadata_file"]["url"].startswith("/dash/api/experiments/pubsh/files/")
            roles = {f["role"] for f in result["files"]}
            assert roles == {"structure", "topology", "trajectory"}
            paths = {f["path"] for f in result["files"]}
            assert "my_struct.pdb" in paths
            assert "my_top.tpr" in paths
            assert "my_traj.xtc" in paths

    def test_metadata_yaml_contains_expected_fields(self, app: Flask, tmp_path: Path) -> None:
        """Test test_metadata_yaml_contains_expected_fields."""
        _seed_experiment(app)
        exp_dir = tmp_path / "pubsh"
        exp_dir.mkdir(parents=True, exist_ok=True)
        (exp_dir / "s.pdb").write_text("ATOM")
        (exp_dir / "t.tpr").write_bytes(b"\x00" * 16)
        (exp_dir / "r.xtc").write_bytes(b"\x00" * 16)
        sim_path = _write_gmx_simulation(
            exp_dir, files={"run_input": "t.tpr", "reference_structure": "s.pdb", "trajectory": "r.xtc"}
        )

        with (
            patch("models.experiment.DATA_DIR", tmp_path),
            patch("models.simulation.DATA_DIR", tmp_path),
            patch("models.experiment.MDPOSIT_VRE_LITE_URL", ""),
            app.app_context(),
        ):
            exp = Experiment.query.get("pubsh")
            result = exp.publish(target="mdposit", simulation_path=sim_path)

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

    def test_missing_role_key(self, app: Flask, tmp_path: Path) -> None:
        """Simulation missing a file role should raise BadRequest."""
        _seed_experiment(app)
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

        with (
            patch("models.experiment.DATA_DIR", tmp_path),
            patch("models.simulation.DATA_DIR", tmp_path),
            app.app_context(),
        ):
            exp = Experiment.query.get("pubsh")
            with pytest.raises(BadRequest, match=r"Invalid simulation"):
                exp.publish(target="mdposit", simulation_path=sim_path)

    def test_nonexistent_selected_file(self, app: Flask, tmp_path: Path) -> None:
        """Simulation pointing to a nonexistent file should raise BadRequest."""
        _seed_experiment(app)
        exp_dir = tmp_path / "pubsh"
        exp_dir.mkdir(parents=True, exist_ok=True)
        (exp_dir / "topol.tpr").write_bytes(b"\x00" * 16)
        (exp_dir / "traj.xtc").write_bytes(b"\x00" * 16)
        sim_path = _write_gmx_simulation(
            exp_dir,
            files={"run_input": "topol.tpr", "reference_structure": "ghost.pdb", "trajectory": "traj.xtc"},
        )

        with (
            patch("models.experiment.DATA_DIR", tmp_path),
            patch("models.simulation.DATA_DIR", tmp_path),
            app.app_context(),
        ):
            exp = Experiment.query.get("pubsh")
            with pytest.raises(BadRequest, match="Missing files"):
                exp.publish(target="mdposit", simulation_path=sim_path)

    def test_unsupported_extension(self, app: Flask, tmp_path: Path) -> None:
        """File with wrong extension for its role should raise BadRequest."""
        _seed_experiment(app)
        exp_dir = tmp_path / "pubsh"
        exp_dir.mkdir(parents=True, exist_ok=True)
        (exp_dir / "struct.txt").write_text("not a structure")
        (exp_dir / "topol.tpr").write_bytes(b"\x00" * 16)
        (exp_dir / "traj.xtc").write_bytes(b"\x00" * 16)
        sim_path = _write_gmx_simulation(
            exp_dir,
            files={"run_input": "topol.tpr", "reference_structure": "struct.txt", "trajectory": "traj.xtc"},
        )

        with (
            patch("models.experiment.DATA_DIR", tmp_path),
            patch("models.simulation.DATA_DIR", tmp_path),
            app.app_context(),
        ):
            exp = Experiment.query.get("pubsh")
            with pytest.raises(BadRequest, match="Invalid file extension for role 'reference_structure'"):
                exp.publish(target="mdposit", simulation_path=sim_path)

    def test_route_returns_400_for_missing_simulation_path(self, app: Flask, tmp_path: Path) -> None:
        """Route handler should return 400 when simulation_path is missing for mdposit target."""
        _seed_experiment(app)
        (tmp_path / "pubsh").mkdir(parents=True, exist_ok=True)

        with app.test_client() as c:
            resp = c.post(
                "/dash/api/experiments/pubsh/publish",
                json={"target": "mdposit"},
                content_type="application/json",
            )
            assert resp.status_code == HTTPStatus.BAD_REQUEST

    def test_unknown_target_returns_400(self, app: Flask, tmp_path: Path) -> None:
        """Unknown publish target should return 400."""
        _seed_experiment(app)
        (tmp_path / "pubsh").mkdir(parents=True, exist_ok=True)

        with app.test_client() as c:
            resp = c.post(
                "/dash/api/experiments/pubsh/publish",
                json={"target": "unknown_target"},
                content_type="application/json",
            )
            assert resp.status_code == HTTPStatus.BAD_REQUEST


class TestImportMdpositRepo:
    """Tests for _import_mdposit_repo called via Experiment.from_repo."""

    @patch("models.experiment.mdposit.download_project")
    @patch("models.experiment.mdposit.get_project", return_value={"accession": "PRJ1"})
    @patch("models.experiment.mdposit.is_mdposit_url", return_value=True)
    @patch("models.experiment.download_git_repo")
    def test_from_repo_mdposit_creates_experiment(
        self,
        mock_clone: Mock,
        mock_is_url: Mock,
        mock_get_proj: Mock,
        mock_dl_proj: Mock,
        app: Flask,
        tmp_path: Path,
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
            patch("models.experiment.resolve_repo_link", return_value="https://mdposit.mddbr.eu/projects/PRJ1"),
            patch("models.experiment.mdposit.extract_accession", return_value="PRJ1"),
            patch("models.experiment.DATA_DIR", tmp_path),
            patch("models.simulation.DATA_DIR", tmp_path),
            app.app_context(),
            patch("models.experiment.Experiment.prepare_env", return_value="mpcr1"),
        ):
            exp = Experiment.from_repo(
                name="MDPosit Import",
                repo_link="https://mdposit.mddbr.eu/projects/PRJ1",
                notebooks_repo="https://github.com/t/r.git",
            )
            assert exp is not None
            assert exp.name == "MDPosit Import"
            mock_get_proj.assert_called_once_with("PRJ1")

    @patch("models.experiment.mdposit.extract_accession", return_value="")
    @patch("models.experiment.mdposit.is_mdposit_url", return_value=True)
    @patch("models.experiment.download_git_repo")
    def test_from_repo_mdposit_missing_accession_raises(
        self,
        mock_clone: Mock,
        mock_is_url: Mock,
        mock_extract: Mock,
        app: Flask,
        tmp_path: Path,
    ) -> None:
        """Test test_from_repo_mdposit_missing_accession_raises."""
        (tmp_path / "mpacc1").mkdir(parents=True, exist_ok=True)

        with (
            patch("models.experiment.resolve_repo_link", return_value="https://mdposit.mddbr.eu/"),
            patch("models.experiment.DATA_DIR", tmp_path),
            patch("models.simulation.DATA_DIR", tmp_path),
            app.app_context(),
            patch("models.experiment.Experiment.prepare_env", return_value="mpacc1"),
            pytest.raises(BadRequest, match="Missing MDPosit project accession"),
        ):
            Experiment.from_repo(
                name="Bad Accession",
                repo_link="https://mdposit.mddbr.eu/",
                notebooks_repo="https://github.com/t/r.git",
            )

    @patch("models.experiment.mdposit.download_project", side_effect=ValueError("No files found"))
    @patch("models.experiment.mdposit.get_project", return_value={"accession": "EMPTY"})
    @patch("models.experiment.mdposit.is_mdposit_url", return_value=True)
    @patch("models.experiment.download_git_repo")
    def test_from_repo_mdposit_no_files_raises(
        self,
        mock_clone: Mock,
        mock_is_url: Mock,
        mock_get_proj: Mock,
        mock_dl_proj: Mock,
        app: Flask,
        tmp_path: Path,
    ) -> None:
        """Test test_from_repo_mdposit_no_files_raises."""
        (tmp_path / "mpnf1").mkdir(parents=True, exist_ok=True)

        with (
            patch("models.experiment.resolve_repo_link", return_value="https://mdposit.mddbr.eu/projects/EMPTY"),
            patch("models.experiment.mdposit.extract_accession", return_value="EMPTY"),
            patch("models.experiment.DATA_DIR", tmp_path),
            patch("models.simulation.DATA_DIR", tmp_path),
            app.app_context(),
            patch("models.experiment.Experiment.prepare_env", return_value="mpnf1"),
            pytest.raises(BadRequest, match="No files found"),
        ):
            Experiment.from_repo(
                name="No Files",
                repo_link="https://mdposit.mddbr.eu/projects/EMPTY",
                notebooks_repo="https://github.com/t/r.git",
            )


class TestFromRepoRouting:
    """from_repo delegates to _import_mdposit_repo or _import_invenio_repo based on URL."""

    @patch("models.experiment.import_invenio_repo")
    @patch("models.experiment.mdposit.is_mdposit_url", return_value=False)
    @patch("models.experiment.download_git_repo")
    def test_from_repo_invenio_url(
        self,
        mock_clone: Mock,
        mock_is: Mock,
        mock_import: Mock,
        app: Flask,
        tmp_path: Path,
    ) -> None:
        """Test test_from_repo_invenio_url."""
        (tmp_path / "inv01").mkdir(parents=True, exist_ok=True)

        with (
            patch("models.experiment.resolve_repo_link", return_value="https://zenodo.org/records/12345"),
            patch("models.experiment.DATA_DIR", tmp_path),
            patch("models.simulation.DATA_DIR", tmp_path),
            app.app_context(),
            patch("models.experiment.Experiment.prepare_env", return_value="inv01"),
        ):
            Experiment.from_repo(
                name="Invenio Repo",
                repo_link="https://zenodo.org/records/12345",
                notebooks_repo="https://github.com/t/r.git",
            )
            mock_import.assert_called_once()

    @patch("models.experiment.import_mdposit_repo")
    @patch("models.experiment.mdposit.is_mdposit_url", return_value=True)
    @patch("models.experiment.download_git_repo")
    def test_from_repo_mdposit_url(
        self,
        mock_clone: Mock,
        mock_is: Mock,
        mock_import: Mock,
        app: Flask,
        tmp_path: Path,
    ) -> None:
        """Test test_from_repo_mdposit_url."""
        (tmp_path / "mp01").mkdir(parents=True, exist_ok=True)

        with (
            patch("models.experiment.resolve_repo_link", return_value="https://mdposit.mddbr.eu/projects/P1"),
            patch("models.experiment.DATA_DIR", tmp_path),
            patch("models.simulation.DATA_DIR", tmp_path),
            app.app_context(),
            patch("models.experiment.Experiment.prepare_env", return_value="mp01"),
        ):
            Experiment.from_repo(
                name="MDPosit Repo",
                repo_link="https://mdposit.mddbr.eu/projects/P1",
                notebooks_repo="https://github.com/t/r.git",
            )
            mock_import.assert_called_once()
