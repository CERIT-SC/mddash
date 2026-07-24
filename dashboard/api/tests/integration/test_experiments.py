"""
Integration tests for experiment API routes.

Tests the full request/response cycle with mocked external dependencies.
"""

import io
import json
from http import HTTPStatus
from pathlib import Path
from unittest.mock import MagicMock, patch

from flask.testing import FlaskClient
from models import Experiment, Notebook
from sqlalchemy.orm import Session
from werkzeug.exceptions import InternalServerError
from werkzeug.utils import secure_filename

EXPERIMENT_ID_LENGTH = 5


class TestListExperiments:
    """Tests for GET /api/experiments."""

    def test_returns_empty_list_initially(self, client: FlaskClient) -> None:
        """Should return empty list when no experiments exist."""
        response = client.get("/dash/api/experiments")

        assert response.status_code == HTTPStatus.OK
        data = json.loads(response.data)
        assert data == []

    def test_returns_experiments(self, client: FlaskClient, db_session: Session) -> None:
        """Should return list of all experiments."""
        # Create test experiment directly in DB
        exp = Experiment()
        exp.id = "testx"
        exp.name = "Test Experiment"
        exp.source_message = "Test"
        db_session.add(exp)
        db_session.flush()

        notebook = Notebook()
        notebook.experiment_id = "testx"
        db_session.add(notebook)
        db_session.commit()

        response = client.get("/dash/api/experiments")

        assert response.status_code == HTTPStatus.OK
        data = json.loads(response.data)
        assert len(data) == 1
        assert data[0]["id"] == "testx"
        assert data[0]["name"] == "Test Experiment"


class TestGetExperiment:
    """Tests for GET /api/experiments/<id>."""

    def test_returns_experiment_by_id(self, client: FlaskClient, db_session: Session) -> None:
        """Should return experiment details for valid ID."""
        exp = Experiment()
        exp.id = "abcde"
        exp.name = "My Experiment"
        exp.source_message = "Created for test"
        db_session.add(exp)
        db_session.flush()

        notebook = Notebook()
        notebook.experiment_id = "abcde"
        db_session.add(notebook)
        db_session.commit()

        response = client.get("/dash/api/experiments/abcde")

        assert response.status_code == HTTPStatus.OK
        data = json.loads(response.data)
        assert data["id"] == "abcde"
        assert data["name"] == "My Experiment"

    def test_returns_404_for_missing_experiment(self, client: FlaskClient) -> None:
        """Should return 404 for non-existent experiment ID."""
        response = client.get("/dash/api/experiments/zzzzz")

        assert response.status_code == HTTPStatus.NOT_FOUND


class TestCreateExperiment:
    """Tests for POST /api/experiments."""

    def test_create_from_pdb_success(self, client: FlaskClient, sample_pdb_content: bytes, tmp_path: Path) -> None:
        """Should create experiment from valid PDB ID."""
        with (
            patch("models.experiment.requests.get") as mock_get,
            patch("models.experiment.DATA_DIR", tmp_path),
            patch("models.experiment.download_git_repo") as mock_clone,
        ):
            # Mock successful PDB download
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.content = sample_pdb_content
            mock_get.return_value = mock_response

            response = client.post(
                "/dash/api/experiments",
                data={
                    "type": "pdb",
                    "experiment-name": "Test PDB Experiment",
                    "pdb": "1ABC",
                    "notebooks-repo": "https://github.com/test/repo.git",
                },
            )

            assert response.status_code == HTTPStatus.CREATED
            data = json.loads(response.data)
            assert data["name"] == "Test PDB Experiment"
            assert data["notebooks_repo"] == "https://github.com/test/repo.git"
            assert len(data["id"]) == EXPERIMENT_ID_LENGTH
            mock_clone.assert_called_once()

    def test_create_from_pdb_not_found(self, client: FlaskClient, tmp_path: Path) -> None:
        """Should return 404 when PDB ID doesn't exist."""
        with (
            patch("models.experiment.requests.get") as mock_get,
            patch("models.experiment.DATA_DIR", tmp_path),
            patch("models.experiment.download_git_repo"),
        ):
            mock_response = MagicMock()
            mock_response.status_code = 404
            mock_get.return_value = mock_response

            response = client.post(
                "/dash/api/experiments",
                data={
                    "type": "pdb",
                    "experiment-name": "Invalid PDB",
                    "pdb": "XXXX",
                    "notebooks-repo": "https://github.com/test/repo.git",
                },
            )

            assert response.status_code == HTTPStatus.NOT_FOUND

    def test_create_from_pdb_url_success(self, client: FlaskClient, sample_pdb_content: bytes, tmp_path: Path) -> None:
        """Should create experiment from a direct URL to a PDB file."""
        pdb_url = "https://www.ebi.ac.uk/pdbe/entry-files/download/pdb3vte.ent"
        with (
            patch("models.experiment.requests.get") as mock_get,
            patch("models.experiment.DATA_DIR", tmp_path),
            patch("models.experiment.download_git_repo") as mock_clone,
            patch("validators._getaddrinfo_ips", return_value=["193.62.193.80"]),
        ):
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.content = sample_pdb_content
            mock_get.return_value = mock_response

            response = client.post(
                "/dash/api/experiments",
                data={
                    "type": "pdb",
                    "experiment-name": "PDB URL Experiment",
                    "pdb": pdb_url,
                    "notebooks-repo": "https://github.com/test/repo.git",
                },
            )

            assert response.status_code == HTTPStatus.CREATED
            data = json.loads(response.data)
            assert data["name"] == "PDB URL Experiment"
            assert pdb_url in data["source_message"]
            assert len(data["id"]) == EXPERIMENT_ID_LENGTH
            # The URL should be fetched directly, not the RCSB ID URL
            mock_get.assert_called_once_with(pdb_url, timeout=30, allow_redirects=False)
            mock_clone.assert_called_once()

    def test_create_from_pdb_url_rejects_html_response(self, client: FlaskClient, tmp_path: Path) -> None:
        """Should return 400 when a PDB URL returns HTML instead of a PDB file."""
        pdb_url = "https://example.org/login"
        html_content = b"<!DOCTYPE html><html><body>Please log in</body></html>"
        with (
            patch("models.experiment.requests.get") as mock_get,
            patch("models.experiment.DATA_DIR", tmp_path),
            patch("models.experiment.download_git_repo"),
            patch("validators._getaddrinfo_ips", return_value=["93.184.216.34"]),
        ):
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.content = html_content
            mock_get.return_value = mock_response

            response = client.post(
                "/dash/api/experiments",
                data={
                    "type": "pdb",
                    "experiment-name": "HTML Response",
                    "pdb": pdb_url,
                    "notebooks-repo": "https://github.com/test/repo.git",
                },
            )

            assert response.status_code == HTTPStatus.BAD_REQUEST
            # The invalid content must not be persisted as input.pdb
            assert not any((tmp_path / d / "input.pdb").exists() for d in tmp_path.iterdir() if d.is_dir())

    def test_create_from_pdb_id_rejects_non_pdb_response(self, client: FlaskClient, tmp_path: Path) -> None:
        """Should return 400 when an RCSB PDB ID returns non-PDB content."""
        with (
            patch("models.experiment.requests.get") as mock_get,
            patch("models.experiment.DATA_DIR", tmp_path),
            patch("models.experiment.download_git_repo"),
        ):
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.content = b"<html><body>not a pdb</body></html>"
            mock_get.return_value = mock_response

            response = client.post(
                "/dash/api/experiments",
                data={
                    "type": "pdb",
                    "experiment-name": "Bad RCSB",
                    "pdb": "1ABC",
                    "notebooks-repo": "https://github.com/test/repo.git",
                },
            )

            assert response.status_code == HTTPStatus.BAD_REQUEST
            mock_get.assert_called_once_with(
                "https://files.rcsb.org/download/1ABC.pdb", timeout=30, allow_redirects=False
            )

    def test_create_from_pdb_url_not_found(self, client: FlaskClient, tmp_path: Path) -> None:
        """Should return 404 when a PDB URL returns 404."""
        pdb_url = "https://example.org/missing.pdb"
        with (
            patch("models.experiment.requests.get") as mock_get,
            patch("models.experiment.DATA_DIR", tmp_path),
            patch("models.experiment.download_git_repo"),
            patch("validators._getaddrinfo_ips", return_value=["93.184.216.34"]),
        ):
            mock_response = MagicMock()
            mock_response.status_code = 404
            mock_get.return_value = mock_response

            response = client.post(
                "/dash/api/experiments",
                data={
                    "type": "pdb",
                    "experiment-name": "Missing URL",
                    "pdb": pdb_url,
                    "notebooks-repo": "https://github.com/test/repo.git",
                },
            )

            assert response.status_code == HTTPStatus.NOT_FOUND

    def test_create_from_pdb_url_rejects_file_scheme(self, client: FlaskClient, tmp_path: Path) -> None:
        """Should return 400 when a PDB URL uses a non-http(s) scheme."""
        with (
            patch("models.experiment.requests.get"),
            patch("models.experiment.DATA_DIR", tmp_path),
            patch("models.experiment.download_git_repo"),
        ):
            response = client.post(
                "/dash/api/experiments",
                data={
                    "type": "pdb",
                    "experiment-name": "Bad Scheme",
                    "pdb": "file:///etc/passwd",
                    "notebooks-repo": "https://github.com/test/repo.git",
                },
            )

            assert response.status_code == HTTPStatus.BAD_REQUEST

    def test_create_from_pdb_url_rejects_internal_host(self, client: FlaskClient, tmp_path: Path) -> None:
        """Should return 400 when a PDB URL points at an internal SSRF target."""
        with (
            patch("models.experiment.requests.get") as mock_get,
            patch("models.experiment.DATA_DIR", tmp_path),
            patch("models.experiment.download_git_repo"),
        ):
            response = client.post(
                "/dash/api/experiments",
                data={
                    "type": "pdb",
                    "experiment-name": "SSRF Attempt",
                    "pdb": "http://169.254.169.254/latest/meta-data/",
                    "notebooks-repo": "https://github.com/test/repo.git",
                },
            )

            assert response.status_code == HTTPStatus.BAD_REQUEST
            mock_get.assert_not_called()

    def test_create_from_pdb_url_rejects_hostname_resolving_internal(self, client: FlaskClient, tmp_path: Path) -> None:
        """Should return 400 when a PDB URL hostname resolves to an internal IP."""
        with (
            patch("models.experiment.requests.get") as mock_get,
            patch("models.experiment.DATA_DIR", tmp_path),
            patch("models.experiment.download_git_repo"),
            patch("validators._getaddrinfo_ips", return_value=["10.43.0.1"]),
        ):
            response = client.post(
                "/dash/api/experiments",
                data={
                    "type": "pdb",
                    "experiment-name": "SSRF Hostname",
                    "pdb": "https://kubernetes.default.svc/api",
                    "notebooks-repo": "https://github.com/test/repo.git",
                },
            )

            assert response.status_code == HTTPStatus.BAD_REQUEST
            mock_get.assert_not_called()

    def test_create_from_pdb_url_rejects_redirect_to_internal(self, client: FlaskClient, tmp_path: Path) -> None:
        """Should reject a redirect chain that lands on an internal target."""
        external_url = "https://example.org/pdb3vte.ent"
        internal_url = "http://169.254.169.254/latest/meta-data/"
        with (
            patch("models.experiment.requests.get") as mock_get,
            patch("models.experiment.DATA_DIR", tmp_path),
            patch("models.experiment.download_git_repo"),
            patch("validators._getaddrinfo_ips", return_value=["93.184.216.34"]),
        ):
            redirect_resp = MagicMock()
            redirect_resp.status_code = 302
            redirect_resp.headers = {"Location": internal_url}

            mock_get.side_effect = [redirect_resp]

            response = client.post(
                "/dash/api/experiments",
                data={
                    "type": "pdb",
                    "experiment-name": "Redirect SSRF",
                    "pdb": external_url,
                    "notebooks-repo": "https://github.com/test/repo.git",
                },
            )

            assert response.status_code == HTTPStatus.BAD_REQUEST
            # Only the first (external) hop should have been fetched.
            mock_get.assert_called_once_with(external_url, timeout=30, allow_redirects=False)

    def test_create_uses_default_notebooks_repo(
        self, client: FlaskClient, sample_pdb_content: bytes, tmp_path: Path
    ) -> None:
        """Should use default notebooks repo when not provided."""
        with (
            patch("models.experiment.requests.get") as mock_get,
            patch("models.experiment.DATA_DIR", tmp_path),
            patch("models.experiment.download_git_repo") as mock_clone,
            patch("routes.experiments.DEFAULT_NOTEBOOKS_REPO", "https://github.com/default/repo.git"),
        ):
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.content = sample_pdb_content
            mock_get.return_value = mock_response

            response = client.post(
                "/dash/api/experiments",
                data={
                    "type": "pdb",
                    "experiment-name": "Test Default Repo",
                    "pdb": "1ABC",
                    # No notebooks-repo provided - should use default
                },
            )

            assert response.status_code == HTTPStatus.CREATED
            data = json.loads(response.data)
            assert data["notebooks_repo"] == "https://github.com/default/repo.git"
            mock_clone.assert_called_once()

    def test_create_fails_on_clone_error(self, client: FlaskClient, sample_pdb_content: bytes, tmp_path: Path) -> None:
        """Should return error when git clone fails."""
        with (
            patch("models.experiment.requests.get") as mock_get,
            patch("models.experiment.DATA_DIR", tmp_path),
            patch("models.experiment.download_git_repo") as mock_clone,
        ):
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.content = sample_pdb_content
            mock_get.return_value = mock_response

            mock_clone.side_effect = InternalServerError(description="Failed to clone repository")

            response = client.post(
                "/dash/api/experiments",
                data={
                    "type": "pdb",
                    "experiment-name": "Clone Fail Test",
                    "pdb": "1ABC",
                    "notebooks-repo": "https://github.com/test/repo.git",
                },
            )

            assert response.status_code == HTTPStatus.INTERNAL_SERVER_ERROR

    def test_create_rejects_invalid_notebooks_repo_url(self, client: FlaskClient) -> None:
        """Should return 400 for invalid notebooks repo URL."""
        response = client.post(
            "/dash/api/experiments",
            data={
                "type": "pdb",
                "experiment-name": "Invalid URL Test",
                "pdb": "1ABC",
                "notebooks-repo": "file:///etc/passwd",
            },
        )

        assert response.status_code == HTTPStatus.BAD_REQUEST

    def test_create_invalid_type(self, client: FlaskClient) -> None:
        """Should return 400 for invalid experiment type."""
        response = client.post(
            "/dash/api/experiments",
            data={
                "type": "invalid",
                "experiment-name": "Test",
            },
        )

        assert response.status_code == HTTPStatus.BAD_REQUEST

    def test_create_from_files_success(self, client: FlaskClient, tmp_path: Path) -> None:
        """Should create experiment from uploaded files."""
        with patch("models.experiment.DATA_DIR", tmp_path), patch("models.experiment.download_git_repo") as mock_clone:
            data = {
                "type": "file",
                "experiment-name": "Test File Experiment",
                "notebooks-repo": "https://github.com/test/repo.git",
                "simulation-files": [
                    (io.BytesIO(b"content1"), "test1.gro"),
                    (io.BytesIO(b"content2"), "test2.itp"),
                ],
            }

            response = client.post(
                "/dash/api/experiments",
                data=data,
                content_type="multipart/form-data",
            )

            assert response.status_code == HTTPStatus.CREATED
            data = json.loads(response.data)
            assert data["name"] == "Test File Experiment"
            mock_clone.assert_called_once()

            # Verify files were saved
            exp_id = data["id"]
            exp_dir = tmp_path / exp_id
            assert (exp_dir / "test1.gro").exists()
            assert (exp_dir / "test2.itp").exists()

    def test_create_with_malicious_filenames(self, client: FlaskClient, tmp_path: Path) -> None:
        """Should sanitize malicious filenames during upload."""
        with patch("models.experiment.DATA_DIR", tmp_path), patch("models.experiment.download_git_repo"):
            malicious_filename_1 = "../../../etc/passwd"
            malicious_filename_2 = "<script>alert(1)</script>.js"

            data = {
                "type": "file",
                "experiment-name": "Malicious Files Experiment",
                "notebooks-repo": "https://github.com/test/repo.git",
                "simulation-files": [
                    (io.BytesIO(b"hack"), malicious_filename_1),
                    (io.BytesIO(b"script"), malicious_filename_2),
                ],
            }

            response = client.post(
                "/dash/api/experiments",
                data=data,
                content_type="multipart/form-data",
            )

            assert response.status_code == HTTPStatus.CREATED
            data = json.loads(response.data)

            # Verify files were saved with sanitized names
            exp_id = data["id"]
            exp_dir = tmp_path / exp_id

            expected_name_1 = secure_filename(malicious_filename_1)
            expected_name_2 = secure_filename(malicious_filename_2)

            # Ensure sanitization actually does something
            assert expected_name_1 != malicious_filename_1
            assert expected_name_2 != malicious_filename_2

            assert (exp_dir / expected_name_1).exists()
            assert (exp_dir / expected_name_2).exists()


class TestCreateExperimentCuratedModule:
    """Tests for POST /api/experiments with curated notebook module selection."""

    def test_curated_uses_selective_checkout(
        self, client: FlaskClient, sample_pdb_content: bytes, tmp_path: Path
    ) -> None:
        """Curated creation should use the selective module checkout, not the full clone."""
        with (
            patch("models.experiment.requests.get") as mock_get,
            patch("models.experiment.DATA_DIR", tmp_path),
            patch("models.experiment.download_git_repo") as mock_full,
            patch("models.experiment.download_git_repo_module") as mock_module,
            patch("routes.experiments.DEFAULT_NOTEBOOKS_REPO", "https://github.com/default/repo.git"),
        ):
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.content = sample_pdb_content
            mock_get.return_value = mock_response

            response = client.post(
                "/dash/api/experiments",
                data={
                    "type": "pdb",
                    "experiment-name": "Curated Experiment",
                    "pdb": "1ABC",
                    "engine": "GMX",
                    "notebook-module": "gromacs-protein",
                },
            )

            assert response.status_code == HTTPStatus.CREATED
            mock_full.assert_not_called()
            mock_module.assert_called_once()
            data = json.loads(response.data)
            assert data["notebooks_repo"] == "https://github.com/default/repo.git"

    def test_curated_rejects_invalid_module(self, client: FlaskClient, tmp_path: Path) -> None:
        """Curated creation should reject an unknown or engine-incompatible module ID."""
        with (
            patch("models.experiment.DATA_DIR", tmp_path),
            patch("models.experiment.download_git_repo_module") as mock_module,
        ):
            response = client.post(
                "/dash/api/experiments",
                data={
                    "type": "file",
                    "experiment-name": "Invalid Module",
                    "engine": "AMBER",
                    "notebook-module": "gromacs-protein",
                    "simulation-files": [(io.BytesIO(b"content"), "test.gro")],
                },
                content_type="multipart/form-data",
            )

            assert response.status_code == HTTPStatus.BAD_REQUEST
            mock_module.assert_not_called()

    def test_custom_mode_without_module_uses_full_clone(
        self, client: FlaskClient, sample_pdb_content: bytes, tmp_path: Path
    ) -> None:
        """Without a module ID, custom mode should use the full clone path."""
        with (
            patch("models.experiment.requests.get") as mock_get,
            patch("models.experiment.DATA_DIR", tmp_path),
            patch("models.experiment.download_git_repo") as mock_full,
            patch("models.experiment.download_git_repo_module") as mock_module,
        ):
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.content = sample_pdb_content
            mock_get.return_value = mock_response

            response = client.post(
                "/dash/api/experiments",
                data={
                    "type": "pdb",
                    "experiment-name": "Custom Experiment",
                    "pdb": "1ABC",
                    "notebooks-repo": "https://github.com/custom/repo.git",
                },
            )

            assert response.status_code == HTTPStatus.CREATED
            mock_full.assert_called_once()
            mock_module.assert_not_called()

    def test_curated_module_with_repository_stores_module_url(
        self, client: FlaskClient, sample_pdb_content: bytes, tmp_path: Path
    ) -> None:
        """A curated module with a repository field should store that URL in the experiment."""
        import notebook_modules  # ruff:ignore[import-outside-top-level]

        binder_module = notebook_modules.NotebookModule(
            id="binder-gmx",
            name="Binder",
            description="d",
            engine="GMX",
            path=".",
            repository="https://github.com/bioexcel/biobb_wf_md_setup_membrane.git",
        )
        catalog = notebook_modules.NotebookModulesCatalog(modules=(binder_module,))

        with (
            patch("models.experiment.requests.get") as mock_get,
            patch("models.experiment.DATA_DIR", tmp_path),
            patch("models.experiment.download_git_repo") as mock_full,
            patch("models.experiment.download_git_repo_module") as mock_module,
            patch("routes.experiments.load_catalog", return_value=catalog),
            patch("models.experiment.load_catalog", return_value=catalog),
        ):
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.content = sample_pdb_content
            mock_get.return_value = mock_response

            response = client.post(
                "/dash/api/experiments",
                data={
                    "type": "pdb",
                    "experiment-name": "Binder Experiment",
                    "pdb": "1ABC",
                    "engine": "GMX",
                    "notebook-module": "binder-gmx",
                },
            )

            assert response.status_code == HTTPStatus.CREATED
            data = json.loads(response.data)
            assert data["notebooks_repo"] == "https://github.com/bioexcel/biobb_wf_md_setup_membrane.git"
            # Root-path module uses full clone, not sparse checkout
            mock_full.assert_called_once()
            mock_module.assert_not_called()


class TestEditExperiment:
    """Tests for PATCH /api/experiments/<id>."""

    def test_update_experiment_name(self, client: FlaskClient, db_session: Session) -> None:
        """Should update experiment name."""
        exp = Experiment()
        exp.id = "editx"
        exp.name = "Original Name"
        exp.source_message = "Test"
        db_session.add(exp)
        db_session.flush()

        notebook = Notebook()
        notebook.experiment_id = "editx"
        db_session.add(notebook)
        db_session.commit()

        response = client.patch(
            "/dash/api/experiments/editx",
            json={"name": "Updated Name"},
            content_type="application/json",
        )

        assert response.status_code == HTTPStatus.OK
        data = json.loads(response.data)
        assert data["name"] == "Updated Name"

    def test_update_nonexistent_experiment(self, client: FlaskClient) -> None:
        """Should return 404 when updating non-existent experiment."""
        response = client.patch(
            "/dash/api/experiments/nope1",
            json={"name": "New Name"},
            content_type="application/json",
        )

        assert response.status_code == HTTPStatus.NOT_FOUND

    def test_update_with_no_data(self, client: FlaskClient, db_session: Session) -> None:
        """Should return 400 when no data provided."""
        exp = Experiment()
        exp.id = "nodta"
        exp.name = "Test"
        exp.source_message = "Test"
        db_session.add(exp)
        db_session.flush()

        notebook = Notebook()
        notebook.experiment_id = "nodta"
        db_session.add(notebook)
        db_session.commit()

        response = client.patch(
            "/dash/api/experiments/nodta",
            json={},
            content_type="application/json",
        )

        assert response.status_code == HTTPStatus.BAD_REQUEST


class TestDeleteExperiment:
    """Tests for DELETE /api/experiments/<id>."""

    def test_delete_experiment(self, client: FlaskClient, db_session: Session, tmp_path: Path) -> None:
        """Should delete experiment and return 204."""
        # Create experiment directory
        exp_dir = tmp_path / "delme"
        exp_dir.mkdir()

        with patch("models.experiment.DATA_DIR", tmp_path):
            exp = Experiment()
            exp.id = "delme"
            exp.name = "To Delete"
            exp.source_message = "Test"
            db_session.add(exp)
            db_session.flush()

            notebook = Notebook()
            notebook.experiment_id = "delme"
            db_session.add(notebook)
            db_session.commit()

            response = client.delete("/dash/api/experiments/delme")

            assert response.status_code == HTTPStatus.NO_CONTENT

    def test_delete_nonexistent_experiment(self, client: FlaskClient) -> None:
        """Should return 404 when deleting non-existent experiment."""
        response = client.delete("/dash/api/experiments/nope2")

        assert response.status_code == HTTPStatus.NOT_FOUND
