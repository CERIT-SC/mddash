"""
Integration tests for experiment API routes.

Tests the full request/response cycle with mocked external dependencies.
"""

from http import HTTPStatus
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import respx
from errors import InternalServerError
from httpx import AsyncClient
from models import Experiment, Notebook
from sqlalchemy.ext.asyncio import AsyncSession as Session
from utils import secure_filename

EXPERIMENT_ID_LENGTH = 5


class TestListExperiments:
    """Tests for GET /api/experiments."""

    async def test_returns_empty_list_initially(self, client: AsyncClient) -> None:
        """Should return empty list when no experiments exist."""
        response = await client.get("/dash/api/experiments")

        assert response.status_code == HTTPStatus.OK
        data = response.json()
        assert data == []

    async def test_returns_experiments(self, client: AsyncClient, db_session: Session) -> None:
        """Should return list of all experiments."""
        # Create test experiment directly in DB
        exp = Experiment()
        exp.id = "testx"
        exp.name = "Test Experiment"
        exp.module_category = "membrane-protein"
        db_session.add(exp)
        await db_session.flush()

        notebook = Notebook()
        notebook.experiment_id = "testx"
        db_session.add(notebook)
        await db_session.commit()

        response = await client.get("/dash/api/experiments")

        assert response.status_code == HTTPStatus.OK
        data = response.json()
        assert len(data) == 1
        assert data[0]["id"] == "testx"
        assert data[0]["name"] == "Test Experiment"
        # persisted module identity round-trips (covers rows backfilled by migration 011)
        assert data[0]["module_category"] == "membrane-protein"
        # curated module identity is a name+category snapshot, never an FK
        assert "module_id" not in data[0]

    async def test_embeds_analysis_jobs_as_objects(self, client: AsyncClient, db_session: Session) -> None:
        """Should embed full analysis job objects, not primary-key strings."""
        from enums import AnalysisType, JobStatus
        from models import AnalysisJob

        exp = Experiment()
        exp.id = "testx"
        exp.name = "Test Experiment"
        db_session.add(exp)
        await db_session.flush()

        db_session.add(
            AnalysisJob(
                id="job1",
                experiment_id="testx",
                simulation_path="md.simulation.json",
                analysis_name=AnalysisType.RMSDS,
                trajectory_file="traj.xtc",
                _last_known_status=JobStatus.FINISHED,
            )
        )
        await db_session.commit()

        response = await client.get("/dash/api/experiments")

        assert response.status_code == HTTPStatus.OK
        data = response.json()
        jobs = data[0]["analysis_jobs"]
        assert len(jobs) == 1
        assert isinstance(jobs[0], dict)
        assert jobs[0]["id"] == "job1"
        assert jobs[0]["analysis_name"] == "rmsds"
        assert jobs[0]["status"] == "FINISHED"

    async def test_eager_loads_relations_without_n_plus_one(self, client: AsyncClient, db_session: Session) -> None:
        """The 5s dashboard poll dumps every experiment — job relations must not lazy-load per row."""
        from enums import AnalysisType, DeviceType, JobStatus
        from models import AnalysisJob, GromacsJob, TunerJob
        from sqlalchemy import event

        for exp_id in ("exp01", "exp02"):
            exp = Experiment()
            exp.id = exp_id
            exp.name = f"Test {exp_id}"
            db_session.add(exp)
            await db_session.flush()
            db_session.add(Notebook(experiment_id=exp_id))
            db_session.add(
                GromacsJob(
                    id=f"gmx-{exp_id}",
                    experiment_id=exp_id,
                    simulation_path="md.simulation.json",
                    np=1,
                    ntomp=1,
                    pme=DeviceType.CPU,
                    nb=DeviceType.CPU,
                    _last_known_status=JobStatus.FINISHED,
                )
            )
            db_session.add(
                TunerJob(
                    id=f"tun-{exp_id}",
                    experiment_id=exp_id,
                    simulation_path="md.simulation.json",
                    nsteps=25000,
                    is_stopped=True,
                )
            )
            db_session.add(
                AnalysisJob(
                    id=f"ana-{exp_id}",
                    experiment_id=exp_id,
                    simulation_path="md.simulation.json",
                    analysis_name=AnalysisType.RMSDS,
                    trajectory_file="traj.xtc",
                    _last_known_status=JobStatus.FINISHED,
                )
            )
        await db_session.commit()

        statements: list[str] = []
        engine = db_session.bind.sync_engine

        def count_selects(_conn, _cursor, statement: str, _parameters, _context, _executemany) -> None:
            if statement.lstrip().upper().startswith("SELECT"):
                statements.append(statement)

        event.listen(engine, "before_cursor_execute", count_selects)
        try:
            response = await client.get("/dash/api/experiments")
        finally:
            event.remove(engine, "before_cursor_execute", count_selects)

        assert response.status_code == HTTPStatus.OK
        assert len(response.json()) == 2
        # Eager ceiling: 1 root query + 1 selectin per relation (notebook, tuner, simulation, analysis).
        assert len(statements) <= 6, "lazy per-experiment loads detected:\n" + "\n---\n".join(statements)


class TestGetExperiment:
    """Tests for GET /api/experiments/<id>."""

    async def test_returns_experiment_by_id(self, client: AsyncClient, db_session: Session) -> None:
        """Should return experiment details for valid ID."""
        exp = Experiment()
        exp.id = "abcde"
        exp.name = "My Experiment"
        db_session.add(exp)
        await db_session.flush()

        notebook = Notebook()
        notebook.experiment_id = "abcde"
        db_session.add(notebook)
        await db_session.commit()

        response = await client.get("/dash/api/experiments/abcde")

        assert response.status_code == HTTPStatus.OK
        data = response.json()
        assert data["id"] == "abcde"
        assert data["name"] == "My Experiment"

    async def test_returns_404_for_missing_experiment(self, client: AsyncClient) -> None:
        """Should return 404 for non-existent experiment ID."""
        response = await client.get("/dash/api/experiments/zzzzz")

        assert response.status_code == HTTPStatus.NOT_FOUND


class TestPublishExperiment:
    """Invenio publish is gated server-side by the same can_publish rule the wizard uses."""

    async def test_rejects_when_nothing_publishable(self, client: AsyncClient, db_session: Session) -> None:
        """Authenticated but no finished run and no existing publication → 409, no MDRepo draft."""
        exp = Experiment()
        exp.id = "pubc1"
        exp.name = "Publish Gate"
        db_session.add(exp)
        await db_session.commit()

        token_manager = MagicMock()
        token_manager.get_credentials = AsyncMock(return_value=MagicMock(access_token="valid-token"))
        with patch("routes.experiments.MDRepoTokenManager", return_value=token_manager):
            response = await client.post("/dash/api/experiments/pubc1/publish", json={"target": "invenio"})

        assert response.status_code == HTTPStatus.CONFLICT
        assert response.headers["content-type"].split(";")[0] == "application/problem+json"


class TestCreateExperiment:
    """Tests for POST /api/experiments."""

    async def test_create_from_pdb_success(
        self, http_mock: respx.MockRouter, client: AsyncClient, sample_pdb_content: bytes, tmp_path: Path
    ) -> None:
        """Should create experiment from valid PDB ID."""
        with (
            patch("models.experiment.DATA_DIR", tmp_path),
            patch("models.experiment.download_git_repo") as mock_clone,
        ):
            # Mock successful PDB download
            http_mock.get(url__regex=r".*").mock(return_value=httpx.Response(200, content=sample_pdb_content))

            response = await client.post(
                "/dash/api/experiments",
                data={
                    "type": "pdb",
                    "experiment-name": "Test PDB Experiment",
                    "pdb": "1ABC",
                    "notebooks-repo": "https://github.com/test/repo.git",
                },
            )

            assert response.status_code == HTTPStatus.CREATED
            data = response.json()
            assert data["name"] == "Test PDB Experiment"
            assert data["notebooks_repo"] == "https://github.com/test/repo.git"
            assert len(data["id"]) == EXPERIMENT_ID_LENGTH
            mock_clone.assert_called_once()

    async def test_create_from_pdb_not_found(
        self, http_mock: respx.MockRouter, client: AsyncClient, tmp_path: Path
    ) -> None:
        """Should return 404 when PDB ID doesn't exist."""
        with (
            patch("models.experiment.DATA_DIR", tmp_path),
            patch("models.experiment.download_git_repo"),
        ):
            http_mock.get(url__regex=r".*").mock(return_value=httpx.Response(404))

            response = await client.post(
                "/dash/api/experiments",
                data={
                    "type": "pdb",
                    "experiment-name": "Invalid PDB",
                    "pdb": "XXXX",
                    "notebooks-repo": "https://github.com/test/repo.git",
                },
            )

            assert response.status_code == HTTPStatus.NOT_FOUND

    async def test_create_from_pdb_url_success(
        self, http_mock: respx.MockRouter, client: AsyncClient, sample_pdb_content: bytes, tmp_path: Path
    ) -> None:
        """Should create experiment from a direct URL to a PDB file."""
        pdb_url = "https://www.ebi.ac.uk/pdbe/entry-files/download/pdb3vte.ent"
        with (
            patch("models.experiment.DATA_DIR", tmp_path),
            patch("models.experiment.download_git_repo") as mock_clone,
            patch("validators._getaddrinfo_ips", return_value=["193.62.193.80"]),
        ):
            mock_get = http_mock.get(url__regex=r".*").mock(
                return_value=httpx.Response(200, content=sample_pdb_content)
            )

            response = await client.post(
                "/dash/api/experiments",
                data={
                    "type": "pdb",
                    "experiment-name": "PDB URL Experiment",
                    "pdb": pdb_url,
                    "notebooks-repo": "https://github.com/test/repo.git",
                },
            )

            assert response.status_code == HTTPStatus.CREATED
            data = response.json()
            assert data["name"] == "PDB URL Experiment"
            assert data["source"]["url"] == pdb_url
            assert len(data["id"]) == EXPERIMENT_ID_LENGTH
            # The URL should be fetched directly, not the RCSB ID URL
            assert mock_get.call_count == 1
            assert str(mock_get.calls.last.request.url) == pdb_url
            mock_clone.assert_called_once()

    async def test_create_from_pdb_url_rejects_html_response(
        self, http_mock: respx.MockRouter, client: AsyncClient, tmp_path: Path
    ) -> None:
        """Should return 400 when a PDB URL returns HTML instead of a PDB file."""
        pdb_url = "https://example.org/login"
        html_content = b"<!DOCTYPE html><html><body>Please log in</body></html>"
        with (
            patch("models.experiment.DATA_DIR", tmp_path),
            patch("models.experiment.download_git_repo"),
            patch("validators._getaddrinfo_ips", return_value=["93.184.216.34"]),
        ):
            http_mock.get(url__regex=r".*").mock(return_value=httpx.Response(200, content=html_content))

            response = await client.post(
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
            assert not list(tmp_path.glob("*/input.pdb"))  # ruff:ignore[blocking-path-method-in-async-function]

    async def test_create_from_pdb_id_rejects_non_pdb_response(
        self, http_mock: respx.MockRouter, client: AsyncClient, tmp_path: Path
    ) -> None:
        """Should return 400 when an RCSB PDB ID returns non-PDB content."""
        with (
            patch("models.experiment.DATA_DIR", tmp_path),
            patch("models.experiment.download_git_repo"),
        ):
            mock_get = http_mock.get(url__regex=r".*").mock(
                return_value=httpx.Response(200, content=b"<html><body>not a pdb</body></html>")
            )

            response = await client.post(
                "/dash/api/experiments",
                data={
                    "type": "pdb",
                    "experiment-name": "Bad RCSB",
                    "pdb": "1ABC",
                    "notebooks-repo": "https://github.com/test/repo.git",
                },
            )

            assert response.status_code == HTTPStatus.BAD_REQUEST
            assert mock_get.call_count == 1
            assert str(mock_get.calls.last.request.url) == "https://files.rcsb.org/download/1ABC.pdb"

    async def test_create_from_pdb_url_not_found(
        self, http_mock: respx.MockRouter, client: AsyncClient, tmp_path: Path
    ) -> None:
        """Should return 404 when a PDB URL returns 404."""
        pdb_url = "https://example.org/missing.pdb"
        with (
            patch("models.experiment.DATA_DIR", tmp_path),
            patch("models.experiment.download_git_repo"),
            patch("validators._getaddrinfo_ips", return_value=["93.184.216.34"]),
        ):
            http_mock.get(url__regex=r".*").mock(return_value=httpx.Response(404))

            response = await client.post(
                "/dash/api/experiments",
                data={
                    "type": "pdb",
                    "experiment-name": "Missing URL",
                    "pdb": pdb_url,
                    "notebooks-repo": "https://github.com/test/repo.git",
                },
            )

            assert response.status_code == HTTPStatus.NOT_FOUND

    async def test_create_from_pdb_url_rejects_file_scheme(self, client: AsyncClient, tmp_path: Path) -> None:
        """Should return 400 when a PDB URL uses a non-http(s) scheme."""
        with (
            patch("models.experiment.DATA_DIR", tmp_path),
            patch("models.experiment.download_git_repo"),
        ):
            response = await client.post(
                "/dash/api/experiments",
                data={
                    "type": "pdb",
                    "experiment-name": "Bad Scheme",
                    "pdb": "file:///etc/passwd",
                    "notebooks-repo": "https://github.com/test/repo.git",
                },
            )

            assert response.status_code == HTTPStatus.BAD_REQUEST

    async def test_create_from_pdb_url_rejects_internal_host(
        self, http_mock: respx.MockRouter, client: AsyncClient, tmp_path: Path
    ) -> None:
        """Should return 400 when a PDB URL points at an internal SSRF target."""
        with (
            patch("models.experiment.DATA_DIR", tmp_path),
            patch("models.experiment.download_git_repo"),
        ):
            response = await client.post(
                "/dash/api/experiments",
                data={
                    "type": "pdb",
                    "experiment-name": "SSRF Attempt",
                    "pdb": "http://169.254.169.254/latest/meta-data/",
                    "notebooks-repo": "https://github.com/test/repo.git",
                },
            )

            assert response.status_code == HTTPStatus.BAD_REQUEST
            assert not http_mock.calls

    async def test_create_from_pdb_url_rejects_hostname_resolving_internal(
        self, http_mock: respx.MockRouter, client: AsyncClient, tmp_path: Path
    ) -> None:
        """Should return 400 when a PDB URL hostname resolves to an internal IP."""
        with (
            patch("models.experiment.DATA_DIR", tmp_path),
            patch("models.experiment.download_git_repo"),
            patch("validators._getaddrinfo_ips", return_value=["10.43.0.1"]),
        ):
            response = await client.post(
                "/dash/api/experiments",
                data={
                    "type": "pdb",
                    "experiment-name": "SSRF Hostname",
                    "pdb": "https://kubernetes.default.svc/api",
                    "notebooks-repo": "https://github.com/test/repo.git",
                },
            )

            assert response.status_code == HTTPStatus.BAD_REQUEST
            assert not http_mock.calls

    async def test_create_from_pdb_url_rejects_redirect_to_internal(
        self, http_mock: respx.MockRouter, client: AsyncClient, tmp_path: Path
    ) -> None:
        """Should reject a redirect chain that lands on an internal target."""
        external_url = "https://example.org/pdb3vte.ent"
        internal_url = "http://169.254.169.254/latest/meta-data/"
        with (
            patch("models.experiment.DATA_DIR", tmp_path),
            patch("models.experiment.download_git_repo"),
            patch("validators._getaddrinfo_ips", return_value=["93.184.216.34"]),
        ):
            mock_get = http_mock.get(url__regex=r".*").mock(
                side_effect=[httpx.Response(302, headers={"Location": internal_url})]
            )

            response = await client.post(
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
            assert mock_get.call_count == 1
            assert str(mock_get.calls.last.request.url) == external_url

    async def test_create_uses_default_notebooks_repo(
        self, http_mock: respx.MockRouter, client: AsyncClient, sample_pdb_content: bytes, tmp_path: Path
    ) -> None:
        """Should use default notebooks repo when not provided."""
        with (
            patch("models.experiment.DATA_DIR", tmp_path),
            patch("models.experiment.download_git_repo") as mock_clone,
            patch("routes.experiments.DEFAULT_NOTEBOOKS_REPO", "https://github.com/default/repo.git"),
        ):
            http_mock.get(url__regex=r".*").mock(return_value=httpx.Response(200, content=sample_pdb_content))

            response = await client.post(
                "/dash/api/experiments",
                data={
                    "type": "pdb",
                    "experiment-name": "Test Default Repo",
                    "pdb": "1ABC",
                    # No notebooks-repo provided - should use default
                },
            )

            assert response.status_code == HTTPStatus.CREATED
            data = response.json()
            assert data["notebooks_repo"] == "https://github.com/default/repo.git"
            mock_clone.assert_called_once()

    async def test_create_fails_on_clone_error(
        self, http_mock: respx.MockRouter, client: AsyncClient, sample_pdb_content: bytes, tmp_path: Path
    ) -> None:
        """Should return error when git clone fails."""
        with (
            patch("models.experiment.DATA_DIR", tmp_path),
            patch("models.experiment.download_git_repo") as mock_clone,
        ):
            http_mock.get(url__regex=r".*").mock(return_value=httpx.Response(200, content=sample_pdb_content))

            mock_clone.side_effect = InternalServerError("Failed to clone repository")

            response = await client.post(
                "/dash/api/experiments",
                data={
                    "type": "pdb",
                    "experiment-name": "Clone Fail Test",
                    "pdb": "1ABC",
                    "notebooks-repo": "https://github.com/test/repo.git",
                },
            )

            assert response.status_code == HTTPStatus.INTERNAL_SERVER_ERROR

    async def test_create_rejects_invalid_notebooks_repo_url(self, client: AsyncClient) -> None:
        """Should return 400 for invalid notebooks repo URL."""
        response = await client.post(
            "/dash/api/experiments",
            data={
                "type": "pdb",
                "experiment-name": "Invalid URL Test",
                "pdb": "1ABC",
                "notebooks-repo": "file:///etc/passwd",
            },
        )

        assert response.status_code == HTTPStatus.BAD_REQUEST

    async def test_create_invalid_type(self, client: AsyncClient) -> None:
        """Should return 400 for invalid experiment type."""
        response = await client.post(
            "/dash/api/experiments",
            data={
                "type": "invalid",
                "experiment-name": "Test",
            },
        )

        assert response.status_code == HTTPStatus.BAD_REQUEST

    async def test_create_from_files_success(self, client: AsyncClient, tmp_path: Path) -> None:
        """Should create experiment from uploaded files."""
        with patch("models.experiment.DATA_DIR", tmp_path), patch("models.experiment.download_git_repo") as mock_clone:
            data = {
                "type": "file",
                "experiment-name": "Test File Experiment",
                "notebooks-repo": "https://github.com/test/repo.git",
            }
            files = [("simulation-files", ("test1.gro", b"content1")), ("simulation-files", ("test2.itp", b"content2"))]

            response = await client.post("/dash/api/experiments", data=data, files=files)

            assert response.status_code == HTTPStatus.CREATED
            data = response.json()
            assert data["name"] == "Test File Experiment"
            assert data["module_category"] is None
            assert "module_id" not in data
            mock_clone.assert_called_once()

            # Verify files were saved
            exp_id = data["id"]
            exp_dir = tmp_path / exp_id
            assert (exp_dir / "test1.gro").exists()
            assert (exp_dir / "test2.itp").exists()

    async def test_create_with_malicious_filenames(self, client: AsyncClient, tmp_path: Path) -> None:
        """Should sanitize malicious filenames during upload."""
        with patch("models.experiment.DATA_DIR", tmp_path), patch("models.experiment.download_git_repo"):
            malicious_filename_1 = "../../../etc/passwd"
            malicious_filename_2 = "<script>alert(1)</script>.js"

            data = {
                "type": "file",
                "experiment-name": "Malicious Files Experiment",
                "notebooks-repo": "https://github.com/test/repo.git",
            }
            files = [
                ("simulation-files", (malicious_filename_1, b"hack")),
                ("simulation-files", (malicious_filename_2, b"script")),
            ]

            response = await client.post("/dash/api/experiments", data=data, files=files)

            assert response.status_code == HTTPStatus.CREATED
            data = response.json()

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

    async def test_curated_uses_selective_checkout(
        self, http_mock: respx.MockRouter, client: AsyncClient, sample_pdb_content: bytes, tmp_path: Path
    ) -> None:
        """Curated creation should use the selective module checkout, not the full clone."""
        with (
            patch("models.experiment.DATA_DIR", tmp_path),
            patch("models.experiment.download_git_repo") as mock_full,
            patch("models.experiment.download_git_repo_module") as mock_module,
            patch("routes.experiments.DEFAULT_NOTEBOOKS_REPO", "https://github.com/default/repo.git"),
        ):
            http_mock.get(url__regex=r".*").mock(return_value=httpx.Response(200, content=sample_pdb_content))

            response = await client.post(
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
            data = response.json()
            assert data["notebooks_repo"] == "https://github.com/default/repo.git"
            assert data["module_category"] == "protein"
            assert "module_id" not in data

    async def test_curated_rejects_invalid_module(self, client: AsyncClient, tmp_path: Path) -> None:
        """Curated creation should reject an unknown or engine-incompatible module ID."""
        with (
            patch("models.experiment.DATA_DIR", tmp_path),
            patch("models.experiment.download_git_repo_module") as mock_module,
        ):
            response = await client.post(
                "/dash/api/experiments",
                data={
                    "type": "file",
                    "experiment-name": "Invalid Module",
                    "engine": "AMBER",
                    "notebook-module": "gromacs-protein",
                },
                files=[("simulation-files", ("test.gro", b"content"))],
            )

            assert response.status_code == HTTPStatus.BAD_REQUEST
            mock_module.assert_not_called()

    async def test_custom_mode_without_module_uses_full_clone(
        self, http_mock: respx.MockRouter, client: AsyncClient, sample_pdb_content: bytes, tmp_path: Path
    ) -> None:
        """Without a module ID, custom mode should use the full clone path."""
        with (
            patch("models.experiment.DATA_DIR", tmp_path),
            patch("models.experiment.download_git_repo") as mock_full,
            patch("models.experiment.download_git_repo_module") as mock_module,
        ):
            http_mock.get(url__regex=r".*").mock(return_value=httpx.Response(200, content=sample_pdb_content))

            response = await client.post(
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

    async def test_curated_module_with_repository_stores_module_url(
        self, http_mock: respx.MockRouter, client: AsyncClient, sample_pdb_content: bytes, tmp_path: Path
    ) -> None:
        """A curated module with a repository field should store that URL in the experiment."""
        import notebook_modules

        binder_module = notebook_modules.NotebookModule(
            id="binder-gmx",
            name="Binder",
            description="d",
            engine="GMX",
            author="a",
            category="protein",
            path=".",
            repository="https://github.com/bioexcel/biobb_wf_md_setup_membrane.git",
        )
        catalog = notebook_modules.NotebookModulesCatalog(modules=(binder_module,))

        with (
            patch("models.experiment.DATA_DIR", tmp_path),
            patch("models.experiment.download_git_repo") as mock_full,
            patch("models.experiment.download_git_repo_module") as mock_module,
            patch("routes.experiments.load_catalog", return_value=catalog),
        ):
            http_mock.get(url__regex=r".*").mock(return_value=httpx.Response(200, content=sample_pdb_content))

            response = await client.post(
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
            data = response.json()
            assert data["notebooks_repo"] == "https://github.com/bioexcel/biobb_wf_md_setup_membrane.git"
            # Root-path module uses full clone, not sparse checkout
            mock_full.assert_called_once()
            mock_module.assert_not_called()


class TestEditExperiment:
    """Tests for PATCH /api/experiments/<id>."""

    async def test_update_experiment_name(self, client: AsyncClient, db_session: Session) -> None:
        """Should update experiment name."""
        exp = Experiment()
        exp.id = "editx"
        exp.name = "Original Name"
        db_session.add(exp)
        await db_session.flush()

        notebook = Notebook()
        notebook.experiment_id = "editx"
        db_session.add(notebook)
        await db_session.commit()

        response = await client.patch(
            "/dash/api/experiments/editx",
            json={"name": "Updated Name"},
        )

        assert response.status_code == HTTPStatus.OK
        data = response.json()
        assert data["name"] == "Updated Name"

    async def test_update_nonexistent_experiment(self, client: AsyncClient) -> None:
        """Should return 404 when updating non-existent experiment."""
        response = await client.patch(
            "/dash/api/experiments/nope1",
            json={"name": "New Name"},
        )

        assert response.status_code == HTTPStatus.NOT_FOUND

    async def test_update_with_no_data(self, client: AsyncClient, db_session: Session) -> None:
        """Should return 400 when no data provided."""
        exp = Experiment()
        exp.id = "nodta"
        exp.name = "Test"
        db_session.add(exp)
        await db_session.flush()

        notebook = Notebook()
        notebook.experiment_id = "nodta"
        db_session.add(notebook)
        await db_session.commit()

        response = await client.patch(
            "/dash/api/experiments/nodta",
            json={},
        )

        assert response.status_code == HTTPStatus.BAD_REQUEST


class TestDeleteExperiment:
    """Tests for DELETE /api/experiments/<id>."""

    async def test_delete_experiment(self, client: AsyncClient, db_session: Session, tmp_path: Path) -> None:
        """Should delete experiment and return 204."""
        # Create experiment directory
        exp_dir = tmp_path / "delme"
        exp_dir.mkdir()

        with patch("models.experiment.DATA_DIR", tmp_path):
            exp = Experiment()
            exp.id = "delme"
            exp.name = "To Delete"
            db_session.add(exp)
            await db_session.flush()

            notebook = Notebook()
            notebook.experiment_id = "delme"
            db_session.add(notebook)
            await db_session.commit()

            response = await client.delete("/dash/api/experiments/delme")

            assert response.status_code == HTTPStatus.NO_CONTENT

    async def test_delete_nonexistent_experiment(self, client: AsyncClient) -> None:
        """Should return 404 when deleting non-existent experiment."""
        response = await client.delete("/dash/api/experiments/nope2")

        assert response.status_code == HTTPStatus.NOT_FOUND


class TestPublishStatus:
    """Tests for GET /api/experiments/<id>/publish/status."""

    async def _seed_experiment(self, db_session: Session, tmp_path: Path) -> None:
        """Seed a minimal experiment for status tests."""
        (tmp_path / "pstat").mkdir(parents=True, exist_ok=True)
        exp = Experiment()
        exp.id = "pstat"
        exp.name = "Status Test"
        db_session.add(exp)
        await db_session.flush()
        nb = Notebook()
        nb.experiment_id = "pstat"
        db_session.add(nb)
        await db_session.commit()

    async def test_status_no_upload(self, client: AsyncClient, db_session: Session, tmp_path: Path) -> None:
        """Status with no upload returns null state."""
        with patch("models.experiment.DATA_DIR", tmp_path):
            await self._seed_experiment(db_session, tmp_path)
            response = await client.get("/dash/api/experiments/pstat/publish/status")

        assert response.status_code == HTTPStatus.OK
        data = response.json()
        assert data["upload_state"] is None
        assert data["total_files"] == 0

    @patch("models.experiment.is_upload_active", return_value=True)
    async def test_status_active_upload(
        self, mock_active: MagicMock, client: AsyncClient, db_session: Session, tmp_path: Path
    ) -> None:
        """Status with an active upload reflects the PVC file."""
        from upload.status import create_queued_status, write_status

        with patch("models.experiment.DATA_DIR", tmp_path):
            await self._seed_experiment(db_session, tmp_path)
            status = create_queued_status("att-1")
            write_status(status, "pstat", tmp_path)

            response = await client.get("/dash/api/experiments/pstat/publish/status")

        assert response.status_code == HTTPStatus.OK
        data = response.json()
        assert data["upload_state"] == "queued"
        assert data["upload_attempt_id"] == "att-1"

    @patch("models.experiment.is_upload_active", return_value=False)
    async def test_status_job_missing_reports_failed(
        self, mock_active: MagicMock, client: AsyncClient, db_session: Session, tmp_path: Path
    ) -> None:
        """PVC says running but Job is gone → failed with job_missing reason."""
        from upload.status import UploadState, UploadStatus, write_status

        with patch("models.experiment.DATA_DIR", tmp_path):
            await self._seed_experiment(db_session, tmp_path)
            status = UploadStatus(
                attempt_id="att-1",
                state=UploadState.RUNNING.value,
            )
            write_status(status, "pstat", tmp_path)

            response = await client.get("/dash/api/experiments/pstat/publish/status")

        assert response.status_code == HTTPStatus.OK
        data = response.json()
        assert data["upload_state"] == "failed"
        assert data["reason"] == "job_missing"

    async def test_status_nonexistent_experiment(self, client: AsyncClient) -> None:
        """Status for a non-existent experiment returns 404."""
        response = await client.get("/dash/api/experiments/nope3/publish/status")
        assert response.status_code == HTTPStatus.NOT_FOUND


class TestDeleteDuringUpload:
    """Tests for experiment deletion during active upload."""

    @patch("models.experiment.is_upload_active", return_value=True)
    @patch("models.experiment.read_status")
    async def test_delete_blocked_during_active_upload(
        self, mock_read: MagicMock, mock_active: MagicMock, client: AsyncClient, db_session: Session, tmp_path: Path
    ) -> None:
        """Cannot delete an experiment with an active upload."""
        from upload.status import UploadState

        mock_read.return_value = MagicMock(state=UploadState.RUNNING.value, attempt_id="att-1")

        with patch("models.experiment.DATA_DIR", tmp_path):
            (tmp_path / "delup").mkdir(parents=True, exist_ok=True)
            exp = Experiment()
            exp.id = "delup"
            exp.name = "Upload Active"
            db_session.add(exp)
            await db_session.flush()
            nb = Notebook()
            nb.experiment_id = "delup"
            db_session.add(nb)
            await db_session.commit()

            response = await client.delete("/dash/api/experiments/delup")

        assert response.status_code == HTTPStatus.CONFLICT
