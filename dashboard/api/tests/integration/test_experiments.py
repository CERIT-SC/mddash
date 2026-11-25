"""
Integration tests for experiment API routes.

Tests the full request/response cycle with mocked external dependencies.
"""

import asyncio
import json
from collections.abc import Iterator
from http import HTTPStatus
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import anyio
import httpx
import pytest
import respx
from clients import Clients
from core.enums import PopulationStatus
from core.errors import InternalServerError
from core.utils import secure_filename
from fastapi import FastAPI
from httpx import AsyncClient
from modules.mdrepo.dependencies import get_tokens
from modules.models import Experiment, Notebook
from modules.population.downloader import ERROR_VALIDATION
from modules.population.models import PopulationOperation
from modules.population.receipt import staging_dir, write_receipt
from modules.population.service import _reconcile
from modules.population.submission import job_name
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession as Session
from tests.support import SeedExperiment

EXPERIMENT_ID_LENGTH = 5


@pytest.fixture(autouse=True)
def git() -> Iterator[SimpleNamespace]:
    """Notebook-repo clones never touch the network; tests assert on `git.clone` / `git.clone_module`."""
    with patch("clients.git.GitClient.clone") as clone, patch("clients.git.GitClient.clone_module") as clone_module:
        yield SimpleNamespace(clone=clone, clone_module=clone_module)


def _pdb_form(name: str, pdb: str) -> dict[str, str]:
    return {"type": "pdb", "experiment-name": name, "pdb": pdb, "notebooks-repo": "https://github.com/test/repo.git"}


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
        exp = Experiment(id="testx", name="Test Experiment", module_category="membrane-protein")
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
        from core.enums import AnalysisType, JobStatus
        from modules.models import AnalysisJob

        exp = Experiment(id="testx", name="Test Experiment")
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
        from core.enums import AnalysisType, DeviceType, JobStatus
        from modules.models import AnalysisJob, GromacsJob, TunerJob
        from sqlalchemy import event

        for exp_id in ("exp01", "exp02"):
            exp = Experiment(id=exp_id, name=f"Test {exp_id}")
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
        # Eager ceiling: 1 root query + 1 selectin per relation (notebook, tuner, simulation, analysis, population).
        assert len(statements) <= 7, "lazy per-experiment loads detected:\n" + "\n---\n".join(statements)


class TestGetExperiment:
    """Tests for GET /api/experiments/<id>."""

    async def test_returns_experiment_by_id(self, client: AsyncClient, db_session: Session) -> None:
        """Should return experiment details for valid ID."""
        exp = Experiment(id="abcde", name="My Experiment")
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

    async def test_rejects_when_nothing_publishable(
        self, app: FastAPI, client: AsyncClient, db_session: Session
    ) -> None:
        """Authenticated but no finished run and no existing publication → 409, no MDRepo draft."""
        exp = Experiment(id="pubc1", name="Publish Gate")
        db_session.add(exp)
        await db_session.commit()

        token_manager = MagicMock()
        token_manager.get_credentials = AsyncMock(return_value=MagicMock(access_token="valid-token"))
        app.dependency_overrides[get_tokens] = lambda: token_manager
        response = await client.post("/dash/api/experiments/pubc1/publish", json={"target": "invenio"})

        assert response.status_code == HTTPStatus.CONFLICT
        assert response.headers["content-type"].split(";")[0] == "application/problem+json"


class TestCreateExperiment:
    """Tests for POST /api/experiments."""

    async def test_create_from_pdb_success(
        self,
        http_mock: respx.MockRouter,
        client: AsyncClient,
        sample_pdb_content: bytes,
        tmp_path: Path,
        git: SimpleNamespace,
    ) -> None:
        """Should create experiment from valid PDB ID."""
        # Mock successful PDB download
        http_mock.get(url__regex=r".*").mock(return_value=httpx.Response(200, content=sample_pdb_content))

        response = await client.post(
            "/dash/api/experiments",
            data=_pdb_form("Test PDB Experiment", "1ABC"),
        )

        assert response.status_code == HTTPStatus.CREATED
        data = response.json()
        assert data["name"] == "Test PDB Experiment"
        assert data["notebooks_repo"] == "https://github.com/test/repo.git"
        assert len(data["id"]) == EXPERIMENT_ID_LENGTH
        git.clone.assert_called_once()

    async def test_create_from_pdb_not_found(
        self, http_mock: respx.MockRouter, client: AsyncClient, tmp_path: Path
    ) -> None:
        """Should return 404 when PDB ID doesn't exist."""
        http_mock.get(url__regex=r".*").mock(return_value=httpx.Response(404))

        response = await client.post(
            "/dash/api/experiments",
            data=_pdb_form("Invalid PDB", "XXXX"),
        )

        assert response.status_code == HTTPStatus.NOT_FOUND

    async def test_create_from_pdb_url_success(
        self,
        http_mock: respx.MockRouter,
        client: AsyncClient,
        sample_pdb_content: bytes,
        tmp_path: Path,
        git: SimpleNamespace,
    ) -> None:
        """Should create experiment from a direct URL to a PDB file."""
        pdb_url = "https://www.ebi.ac.uk/pdbe/entry-files/download/pdb3vte.ent"
        with (
            patch("core.validators._getaddrinfo_ips", return_value=["193.62.193.80"]),
        ):
            mock_get = http_mock.get(url__regex=r".*").mock(
                return_value=httpx.Response(200, content=sample_pdb_content)
            )

            response = await client.post(
                "/dash/api/experiments",
                data=_pdb_form("PDB URL Experiment", pdb_url),
            )

            assert response.status_code == HTTPStatus.CREATED
            data = response.json()
            assert data["name"] == "PDB URL Experiment"
            assert data["source"]["url"] == pdb_url
            assert len(data["id"]) == EXPERIMENT_ID_LENGTH
            # The URL should be fetched directly, not the RCSB ID URL
            assert mock_get.call_count == 1
            assert str(mock_get.calls.last.request.url) == pdb_url
            git.clone.assert_called_once()

    async def test_create_from_pdb_url_rejects_html_response(
        self, http_mock: respx.MockRouter, client: AsyncClient, tmp_path: Path
    ) -> None:
        """Should return 400 when a PDB URL returns HTML instead of a PDB file."""
        pdb_url = "https://example.org/login"
        html_content = b"<!DOCTYPE html><html><body>Please log in</body></html>"
        with (
            patch("core.validators._getaddrinfo_ips", return_value=["93.184.216.34"]),
        ):
            http_mock.get(url__regex=r".*").mock(return_value=httpx.Response(200, content=html_content))

            response = await client.post(
                "/dash/api/experiments",
                data=_pdb_form("HTML Response", pdb_url),
            )

            assert response.status_code == HTTPStatus.BAD_REQUEST
            # The invalid content must not be persisted as input.pdb
            assert not list(tmp_path.glob("*/input.pdb"))  # ruff:ignore[blocking-path-method-in-async-function]

    async def test_create_from_pdb_id_rejects_non_pdb_response(
        self, http_mock: respx.MockRouter, client: AsyncClient, tmp_path: Path
    ) -> None:
        """Should return 400 when an RCSB PDB ID returns non-PDB content."""
        mock_get = http_mock.get(url__regex=r".*").mock(
            return_value=httpx.Response(200, content=b"<html><body>not a pdb</body></html>")
        )

        response = await client.post(
            "/dash/api/experiments",
            data=_pdb_form("Bad RCSB", "1ABC"),
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
            patch("core.validators._getaddrinfo_ips", return_value=["93.184.216.34"]),
        ):
            http_mock.get(url__regex=r".*").mock(return_value=httpx.Response(404))

            response = await client.post(
                "/dash/api/experiments",
                data=_pdb_form("Missing URL", pdb_url),
            )

            assert response.status_code == HTTPStatus.NOT_FOUND

    async def test_create_from_pdb_url_rejects_file_scheme(self, client: AsyncClient, tmp_path: Path) -> None:
        """Should return 400 when a PDB URL uses a non-http(s) scheme."""
        response = await client.post(
            "/dash/api/experiments",
            data=_pdb_form("Bad Scheme", "file:///etc/passwd"),
        )

        assert response.status_code == HTTPStatus.BAD_REQUEST

    async def test_create_from_pdb_url_rejects_internal_host(
        self, http_mock: respx.MockRouter, client: AsyncClient, tmp_path: Path
    ) -> None:
        """Should return 400 when a PDB URL points at an internal SSRF target."""
        response = await client.post(
            "/dash/api/experiments",
            data=_pdb_form("SSRF Attempt", "http://169.254.169.254/latest/meta-data/"),
        )

        assert response.status_code == HTTPStatus.BAD_REQUEST
        assert not http_mock.calls

    async def test_create_from_pdb_url_rejects_hostname_resolving_internal(
        self, http_mock: respx.MockRouter, client: AsyncClient, tmp_path: Path
    ) -> None:
        """Should return 400 when a PDB URL hostname resolves to an internal IP."""
        with (
            patch("core.validators._getaddrinfo_ips", return_value=["10.43.0.1"]),
        ):
            response = await client.post(
                "/dash/api/experiments",
                data=_pdb_form("SSRF Hostname", "https://kubernetes.default.svc/api"),
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
            patch("core.validators._getaddrinfo_ips", return_value=["93.184.216.34"]),
        ):
            mock_get = http_mock.get(url__regex=r".*").mock(
                side_effect=[httpx.Response(302, headers={"Location": internal_url})]
            )

            response = await client.post(
                "/dash/api/experiments",
                data=_pdb_form("Redirect SSRF", external_url),
            )

            assert response.status_code == HTTPStatus.BAD_REQUEST
            # Only the first (external) hop should have been fetched.
            assert mock_get.call_count == 1
            assert str(mock_get.calls.last.request.url) == external_url

    async def test_create_uses_default_notebooks_repo(
        self,
        http_mock: respx.MockRouter,
        client: AsyncClient,
        sample_pdb_content: bytes,
        tmp_path: Path,
        git: SimpleNamespace,
    ) -> None:
        """Should use default notebooks repo when not provided."""
        with (
            patch("modules.experiments.service.DEFAULT_NOTEBOOKS_REPO", "https://github.com/default/repo.git"),
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
            git.clone.assert_called_once()

    async def test_create_fails_on_clone_error(
        self,
        http_mock: respx.MockRouter,
        client: AsyncClient,
        sample_pdb_content: bytes,
        tmp_path: Path,
        git: SimpleNamespace,
    ) -> None:
        """Should return error when git clone fails."""
        http_mock.get(url__regex=r".*").mock(return_value=httpx.Response(200, content=sample_pdb_content))

        git.clone.side_effect = InternalServerError("Failed to clone repository")

        response = await client.post(
            "/dash/api/experiments",
            data=_pdb_form("Clone Fail Test", "1ABC"),
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

    async def test_create_from_files_success(self, client: AsyncClient, tmp_path: Path, git: SimpleNamespace) -> None:
        """Should create experiment from uploaded files."""
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
        git.clone.assert_called_once()

        # Verify files were saved
        exp_id = data["id"]
        exp_dir = tmp_path / exp_id
        assert (exp_dir / "test1.gro").exists()
        assert (exp_dir / "test2.itp").exists()

    async def test_create_with_malicious_filenames(self, client: AsyncClient, tmp_path: Path) -> None:
        """Should sanitize malicious filenames during upload."""
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
        self,
        http_mock: respx.MockRouter,
        client: AsyncClient,
        sample_pdb_content: bytes,
        tmp_path: Path,
        git: SimpleNamespace,
    ) -> None:
        """Curated creation should use the selective module checkout, not the full clone."""
        with (
            patch("modules.experiments.service.DEFAULT_NOTEBOOKS_REPO", "https://github.com/default/repo.git"),
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
            git.clone.assert_not_called()
            git.clone_module.assert_called_once()
            data = response.json()
            assert data["notebooks_repo"] == "https://github.com/default/repo.git"
            assert data["module_category"] == "protein"
            assert "module_id" not in data

    async def test_curated_rejects_invalid_module(
        self, client: AsyncClient, tmp_path: Path, git: SimpleNamespace
    ) -> None:
        """Curated creation should reject an unknown or engine-incompatible module ID."""
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
        git.clone_module.assert_not_called()

    async def test_custom_mode_without_module_uses_full_clone(
        self,
        http_mock: respx.MockRouter,
        client: AsyncClient,
        sample_pdb_content: bytes,
        tmp_path: Path,
        git: SimpleNamespace,
    ) -> None:
        """Without a module ID, custom mode should use the full clone path."""
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
        git.clone.assert_called_once()
        git.clone_module.assert_not_called()

    async def test_curated_module_with_repository_stores_module_url(
        self,
        http_mock: respx.MockRouter,
        client: AsyncClient,
        sample_pdb_content: bytes,
        tmp_path: Path,
        git: SimpleNamespace,
    ) -> None:
        """A curated module with a repository field should store that URL in the experiment."""
        from modules.notebooks import catalog as notebook_modules

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
            patch("modules.experiments.service.load_catalog", return_value=catalog),
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
            git.clone.assert_called_once()
            git.clone_module.assert_not_called()


def _datahugger_form(name: str = "Datahugger Experiment", **fields: str | None) -> dict[str, str]:
    """Multipart form for a Datahugger creation (a None value drops the field)."""
    form: dict[str, str] = {
        "type": "datahugger",
        "experiment-name": name,
        "repo-url": "https://github.com/test/dataset",
        "notebooks-repo": "https://github.com/test/repo.git",
    }
    for key, value in fields.items():
        form_key = key.replace("_", "-")
        if value is not None:
            form[form_key] = value
        else:
            form.pop(form_key, None)
    return form


def _subdir_names(path: Path) -> list[str]:
    """Subdirectory names via a sync helper so pathlib stays off the event loop in async tests."""
    return [p.name for p in path.iterdir() if p.is_dir()]


@pytest.fixture
def population_k8s(clients: Clients, mock_k8s: tuple[AsyncMock, AsyncMock]) -> Iterator[SimpleNamespace]:
    """Admit population pods at once and report deleted worker Jobs as gone at once."""
    with (
        patch.object(clients.k8s, "wait_for_pod_admission", AsyncMock(return_value=True)) as admit,
        patch.object(clients.k8s, "wait_for_resource_absence", AsyncMock(return_value=True)),
    ):
        # A completed worker Job unless a test scripts another state.
        mock_k8s[1].read_namespaced_job.return_value = SimpleNamespace(
            status=SimpleNamespace(
                conditions=[SimpleNamespace(type="Complete", status="True")], active=0, succeeded=1, failed=0
            )
        )
        yield SimpleNamespace(admit=admit, batch_v1=mock_k8s[1])


class TestCreateDatahugger:
    """Tests for POST /api/experiments with type=datahugger (asynchronous population)."""

    async def test_create_datahugger_returns_202_and_submits_worker(
        self,
        client: AsyncClient,
        db_session: Session,
        git: SimpleNamespace,
        population_k8s: SimpleNamespace,
    ) -> None:
        """Queues a population: 202 with identifiers, notebooks prepared, provisional experiment committed."""
        response = await client.post("/dash/api/experiments", data=_datahugger_form())

        assert response.status_code == HTTPStatus.ACCEPTED
        data = response.json()
        assert len(data["operation_id"]) == 16
        assert len(data["experiment_id"]) == EXPERIMENT_ID_LENGTH

        # Notebooks are prepared synchronously, before the 202.
        git.clone.assert_called_once()

        # The one-shot worker Job is submitted under its deterministic name and admitted.
        batch_v1 = population_k8s.batch_v1
        batch_v1.create_namespaced_job.assert_awaited_once()
        manifest = batch_v1.create_namespaced_job.await_args.kwargs["body"]
        assert manifest["metadata"]["name"] == job_name(data["operation_id"])
        population_k8s.admit.assert_awaited_once()

        # The provisional experiment is immediately visible with its queued population.
        listed = (await client.get("/dash/api/experiments")).json()
        assert [e["id"] for e in listed] == [data["experiment_id"]]
        assert listed[0]["population"]["status"] == "queued"
        assert listed[0]["population"]["operation_id"] == data["operation_id"]
        detail = (await client.get(f"/dash/api/experiments/{data['experiment_id']}")).json()
        assert detail["population"]["phase"] == "starting"
        assert detail["population"]["files_present"] == 0
        assert detail["population"]["byte_percentage"] is None

        operation = (await db_session.execute(select(PopulationOperation))).scalars().one()
        assert operation.status is PopulationStatus.queued
        assert operation.repo_url == "https://github.com/test/dataset"
        assert operation.job_name == job_name(operation.id)

    async def test_create_datahugger_worker_manifest_is_tokenless_and_bounded(
        self, client: AsyncClient, git: SimpleNamespace, population_k8s: SimpleNamespace
    ) -> None:
        """The worker reuses the API image, is bounded and non-root, and carries no credentials."""
        response = await client.post(
            "/dash/api/experiments",
            data=_datahugger_form(access_token="secret-notebook-token"),
        )

        assert response.status_code == HTTPStatus.ACCEPTED
        data = response.json()
        manifest = population_k8s.batch_v1.create_namespaced_job.await_args.kwargs["body"]
        pod_spec = manifest["spec"]["template"]["spec"]
        container = pod_spec["containers"][0]

        # The Dashboard API image runs the worker; only public arguments travel with it.
        assert container["image"] == "test-api"
        assert container["command"] == ["python", "-m", "modules.population.worker"]
        assert container["args"] == [
            "--operation-id",
            data["operation_id"],
            "--experiment-id",
            data["experiment_id"],
            "--repo-url",
            "https://github.com/test/dataset",
        ]
        # The worker imports core.config through its receipt helpers; this required
        # non-secret setting must be present or it exits before the first receipt.
        assert container["env"] == [{"name": "NS_MAX_NOTEBOOKS", "value": "2"}]
        assert "secret-notebook-token" not in json.dumps(manifest)

        # Bounded, retry-free, non-root, on the shared PVC.
        assert manifest["spec"]["backoffLimit"] == 0
        assert manifest["spec"]["activeDeadlineSeconds"] == 86400
        assert pod_spec["restartPolicy"] == "Never"
        assert pod_spec["automountServiceAccountToken"] is False
        assert pod_spec["securityContext"]["runAsNonRoot"] is True
        assert container["securityContext"]["runAsUser"] == 1000
        assert container["securityContext"]["runAsGroup"] == 1000
        assert pod_spec["volumes"][0]["persistentVolumeClaim"]["claimName"] == "test-pvc"
        assert container["volumeMounts"][0]["mountPath"] == "/mddash"

    async def test_create_datahugger_curated_module_resolves_server_side(
        self,
        client: AsyncClient,
        db_session: Session,
        tmp_path: Path,
        git: SimpleNamespace,
        population_k8s: SimpleNamespace,
    ) -> None:
        """Curated notebooks use the selective checkout; the client URL is never trusted."""
        with (
            patch("modules.experiments.service.DEFAULT_NOTEBOOKS_REPO", "https://github.com/default/repo.git"),
        ):
            response = await client.post(
                "/dash/api/experiments",
                data=_datahugger_form(notebook_module="gromacs-protein", notebooks_repo=None),
            )

        assert response.status_code == HTTPStatus.ACCEPTED
        git.clone_module.assert_called_once()
        git.clone.assert_not_called()

        operation = (await db_session.execute(select(PopulationOperation))).scalars().one()
        assert operation.notebooks_repo == "https://github.com/default/repo.git"
        assert operation.module_name == "Protein"
        assert operation.module_category == "protein"

    async def test_create_datahugger_missing_repo_url_rejected(
        self, client: AsyncClient, population_k8s: SimpleNamespace
    ) -> None:
        """A datahugger creation without a repository URL is a 400 and submits nothing."""
        response = await client.post("/dash/api/experiments", data=_datahugger_form(repo_url=None))

        assert response.status_code == HTTPStatus.BAD_REQUEST
        population_k8s.batch_v1.create_namespaced_job.assert_not_awaited()

    @pytest.mark.parametrize(
        "repo_url",
        [
            "file:///etc/passwd",
            "https://user:pass@github.com/test/dataset",
        ],
        ids=["non-http-scheme", "embedded-credentials"],
    )
    async def test_create_datahugger_rejects_unsafe_dataset_url(
        self, client: AsyncClient, repo_url: str, population_k8s: SimpleNamespace
    ) -> None:
        """Non-HTTP(S) and credential-bearing dataset URLs are rejected before any side effect."""
        response = await client.post("/dash/api/experiments", data=_datahugger_form(repo_url=repo_url))

        assert response.status_code == HTTPStatus.BAD_REQUEST
        population_k8s.batch_v1.create_namespaced_job.assert_not_awaited()

    async def test_create_datahugger_submission_failure_leaves_no_trace(
        self,
        client: AsyncClient,
        db_session: Session,
        tmp_path: Path,
        clients: Clients,
        population_k8s: SimpleNamespace,
    ) -> None:
        """A submission error returns a safe 500 and rolls back the provisional experiment entirely."""
        with patch.object(clients.k8s, "create_job_raw", AsyncMock(side_effect=RuntimeError("k8s boom"))):
            response = await client.post("/dash/api/experiments", data=_datahugger_form())

        assert response.status_code == HTTPStatus.INTERNAL_SERVER_ERROR
        assert response.headers["content-type"].split(";")[0] == "application/problem+json"
        assert response.json()["detail"] == "The repository download could not be started."

        assert (await db_session.execute(select(PopulationOperation))).scalars().all() == []
        assert (await db_session.execute(select(Experiment))).scalars().all() == []
        # No prepared experiment directory and no staging directory survive (test.db is the DB fixture).
        assert _subdir_names(tmp_path) == []

    async def test_create_datahugger_admission_timeout_leaves_no_trace(
        self,
        client: AsyncClient,
        db_session: Session,
        tmp_path: Path,
        clients: Clients,
        population_k8s: SimpleNamespace,
    ) -> None:
        """A pod that is never admitted deletes the Job and leaves no provisional rows."""
        population_k8s.admit.return_value = False

        response = await client.post("/dash/api/experiments", data=_datahugger_form())

        assert response.status_code == HTTPStatus.INTERNAL_SERVER_ERROR
        assert response.json()["detail"] == "The repository download could not be started."

        assert (await db_session.execute(select(PopulationOperation))).scalars().all() == []
        assert (await db_session.execute(select(Experiment))).scalars().all() == []
        assert not (tmp_path / ".cache").exists()
        population_k8s.batch_v1.delete_namespaced_job.assert_awaited()

    async def test_create_datahugger_cancelled_during_admission_leaves_no_trace(
        self, client: AsyncClient, db_session: Session, tmp_path: Path, population_k8s: SimpleNamespace
    ) -> None:
        """A request cancelled while the pod is admitted deletes the Job, the rows, and the prepared notebooks."""
        population_k8s.admit.side_effect = asyncio.CancelledError

        with pytest.raises(asyncio.CancelledError):
            await client.post("/dash/api/experiments", data=_datahugger_form())

        assert (await db_session.execute(select(PopulationOperation))).scalars().all() == []
        assert (await db_session.execute(select(Experiment))).scalars().all() == []
        assert [p.name async for p in anyio.Path(tmp_path).iterdir() if await p.is_dir() and p.name[0] != "."] == []
        population_k8s.batch_v1.delete_namespaced_job.assert_awaited()


class TestPopulationJobStatus:
    """Tests for GET /api/experiment-population-jobs/<operation_id>."""

    async def test_status_reports_operation(
        self, client: AsyncClient, git: SimpleNamespace, population_k8s: SimpleNamespace
    ) -> None:
        """A queued operation is reported read-only until the monitor reconciles it."""
        created = (await client.post("/dash/api/experiments", data=_datahugger_form())).json()

        response = await client.get(f"/dash/api/experiment-population-jobs/{created['operation_id']}")

        assert response.status_code == HTTPStatus.OK
        assert response.json() == {
            "operation_id": created["operation_id"],
            "experiment_id": created["experiment_id"],
            "status": "queued",
            "phase": "starting",
            "files_present": 0,
            "files_total": None,
            "bytes_present": 0,
            "bytes_total": None,
            "byte_percentage": None,
            "error": None,
        }

    async def test_status_exposes_only_the_curated_failure(
        self,
        client: AsyncClient,
        db_session: Session,
        clients: Clients,
        git: SimpleNamespace,
        population_k8s: SimpleNamespace,
    ) -> None:
        """A failed worker receipt reaches the status response unchanged and without native details."""
        created = (await client.post("/dash/api/experiments", data=_datahugger_form())).json()
        operation = (await db_session.execute(select(PopulationOperation))).scalars().one()
        write_receipt(operation.id, "failed", ERROR_VALIDATION)

        await _reconcile(db_session, clients, operation)
        response = await client.get(f"/dash/api/experiment-population-jobs/{created['operation_id']}")

        assert response.status_code == HTTPStatus.OK
        # The failed receipt carries no phase, so the operation keeps its starting-phase default.
        assert response.json() == {
            "operation_id": created["operation_id"],
            "experiment_id": created["experiment_id"],
            "status": "failed",
            "phase": "starting",
            "files_present": 0,
            "files_total": None,
            "bytes_present": 0,
            "bytes_total": None,
            "byte_percentage": None,
            "error": ERROR_VALIDATION,
        }
        # The failed provisional experiment remains listed with its error.
        listed = (await client.get("/dash/api/experiments")).json()
        assert [e["id"] for e in listed] == [created["experiment_id"]]
        assert listed[0]["population"]["error"] == ERROR_VALIDATION

    async def test_status_unknown_operation_404(self, client: AsyncClient) -> None:
        """An unknown operation ID is a 404."""
        response = await client.get("/dash/api/experiment-population-jobs/ffffffffffffffff")

        assert response.status_code == HTTPStatus.NOT_FOUND


class TestPopulationLifecycle:
    """The provisional experiment is a real experiment: gated while populating, explicitly cancellable."""

    async def _create(self, client: AsyncClient) -> str:
        return (await client.post("/dash/api/experiments", data=_datahugger_form())).json()["experiment_id"]

    async def test_mutations_rejected_while_population_active(
        self, client: AsyncClient, population_k8s: SimpleNamespace
    ) -> None:
        """Every ordinary mutation 409s while the import is unfinished; safe reads stay available."""
        exp_id = await self._create(client)

        mutations = [
            client.patch(f"/dash/api/experiments/{exp_id}", json={"name": "Renamed"}),
            client.delete(f"/dash/api/experiments/{exp_id}"),
            client.post(f"/dash/api/experiments/{exp_id}/notebook"),
            client.delete(f"/dash/api/experiments/{exp_id}/notebook"),
            client.post(
                f"/dash/api/experiments/{exp_id}/simulations",
                json={"name": "s1", "files": {"run_input": "production/input.gro"}},
            ),
            client.post(
                f"/dash/api/experiments/{exp_id}/gmx/production/a.simulation.json",
                json={"np": 2, "ntomp": 2, "pme": "cpu", "nb": "gpu"},
            ),
            client.post(
                f"/dash/api/experiments/{exp_id}/tuner",
                json={"simulation_path": "production/a.simulation.json", "nsteps": 1000},
            ),
            client.post(
                f"/dash/api/experiments/{exp_id}/analysis",
                json={"simulation_path": "production/a.simulation.json", "analysis": "rmsd"},
            ),
            client.post(f"/dash/api/experiments/{exp_id}/publish"),
            client.post(f"/dash/api/experiments/{exp_id}/archive"),
        ]
        for mutation in mutations:
            assert (await mutation).status_code == HTTPStatus.CONFLICT

        reads = [
            client.get(f"/dash/api/experiments/{exp_id}"),
            client.get(f"/dash/api/experiments/{exp_id}/notebook"),
            client.get(f"/dash/api/experiments/{exp_id}/simulations"),
        ]
        for read in reads:
            assert (await read).status_code == HTTPStatus.OK

    async def test_cancel_active_population_deletes_worker_and_keeps_experiment(
        self, client: AsyncClient, tmp_path: Path, population_k8s: SimpleNamespace
    ) -> None:
        """Cancellation confirms the worker is gone, cleans the prepared data, and leaves a durable cancelled state."""
        exp_id = await self._create(client)

        response = await client.post(f"/dash/api/experiments/{exp_id}/population/cancel")

        assert response.status_code == HTTPStatus.OK
        population = response.json()["population"]
        assert population["status"] == "cancelled"
        assert population["phase"] == "cancelling"
        assert population["error"] is None

        # The worker Job was deleted (and its absence waited on); staging and prepared data are gone.
        population_k8s.batch_v1.delete_namespaced_job.assert_awaited_once()
        assert not (tmp_path / ".cache").exists()
        assert not (tmp_path / exp_id).exists()

        # The cancelled experiment stays visible and deletable; a repeated cancellation conflicts.
        listed = (await client.get("/dash/api/experiments")).json()
        assert [e["id"] for e in listed] == [exp_id]
        assert (await client.post(f"/dash/api/experiments/{exp_id}/population/cancel")).status_code == (
            HTTPStatus.CONFLICT
        )
        assert (await client.delete(f"/dash/api/experiments/{exp_id}")).status_code == HTTPStatus.NO_CONTENT

    async def test_cancel_without_population_404(self, client: AsyncClient, seed_experiment: SeedExperiment) -> None:
        """Cancelling an experiment without a Datahugger population is a 404."""
        await seed_experiment("plain1", name="Plain")

        response = await client.post("/dash/api/experiments/plain1/population/cancel")

        assert response.status_code == HTTPStatus.NOT_FOUND

    async def test_cancel_terminal_population_conflicts_and_deletion_cleans_up(
        self,
        client: AsyncClient,
        db_session: Session,
        clients: Clients,
        population_k8s: SimpleNamespace,
    ) -> None:
        """A failed import cannot be cancelled; the failed experiment is deletable and leaves no rows."""
        created = (await client.post("/dash/api/experiments", data=_datahugger_form())).json()
        exp_id = created["experiment_id"]
        operation = (await db_session.execute(select(PopulationOperation))).scalars().one()
        write_receipt(operation.id, "failed", ERROR_VALIDATION)

        await _reconcile(db_session, clients, operation)

        assert (await client.post(f"/dash/api/experiments/{exp_id}/population/cancel")).status_code == (
            HTTPStatus.CONFLICT
        )
        # Terminal (failed) deletion proceeds and removes the linked population row.
        assert (await client.delete(f"/dash/api/experiments/{exp_id}")).status_code == HTTPStatus.NO_CONTENT
        assert (await db_session.execute(select(PopulationOperation))).scalars().all() == []
        assert (await db_session.execute(select(Experiment))).scalars().all() == []

    async def test_succeeded_population_unlocks_mutations(
        self,
        client: AsyncClient,
        db_session: Session,
        clients: Clients,
        tmp_path: Path,
        population_k8s: SimpleNamespace,
    ) -> None:
        """Once the worker is done and the receipt succeeded, the ordinary workflow is unlocked."""
        created = (await client.post("/dash/api/experiments", data=_datahugger_form())).json()
        exp_id = created["experiment_id"]
        operation = (await db_session.execute(select(PopulationOperation))).scalars().one()

        staging = staging_dir(operation.id)
        (staging / "files").mkdir(parents=True)
        (staging / "files" / "data.pdb").write_text("A")
        write_receipt(operation.id, "succeeded")
        await _reconcile(db_session, clients, operation)

        detail = (await client.get(f"/dash/api/experiments/{exp_id}")).json()
        assert detail["population"]["status"] == "succeeded"
        assert (tmp_path / exp_id / "files" / "data.pdb").read_text() == "A"
        # The gated mutation now goes through.
        response = await client.patch(f"/dash/api/experiments/{exp_id}", json={"name": "Ready"})
        assert response.status_code == HTTPStatus.OK
        assert response.json()["name"] == "Ready"


class TestEditExperiment:
    """Tests for PATCH /api/experiments/<id>."""

    async def test_update_experiment_name(self, client: AsyncClient, db_session: Session) -> None:
        """Should update experiment name."""
        exp = Experiment(id="editx", name="Original Name")
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
        exp = Experiment(id="nodta", name="Test")
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

        exp = Experiment(id="delme", name="To Delete")
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

    async def test_status_no_upload(
        self, client: AsyncClient, db_session: Session, tmp_path: Path, seed_experiment: SeedExperiment
    ) -> None:
        """Status with no upload returns null state."""
        await seed_experiment("pstat", name="Status Test")
        response = await client.get("/dash/api/experiments/pstat/publish/status")

        assert response.status_code == HTTPStatus.OK
        data = response.json()
        assert data["upload_state"] is None
        assert data["total_files"] == 0

    @patch("modules.publishing.submission.is_upload_active", return_value=True)
    async def test_status_active_upload(
        self,
        mock_active: MagicMock,
        client: AsyncClient,
        db_session: Session,
        tmp_path: Path,
        seed_experiment: SeedExperiment,
    ) -> None:
        """Status with an active upload reflects the PVC file."""
        from modules.publishing.status import create_queued_status, write_status

        await seed_experiment("pstat", name="Status Test")
        status = create_queued_status("att-1")
        write_status(status, "pstat", tmp_path)

        response = await client.get("/dash/api/experiments/pstat/publish/status")

        assert response.status_code == HTTPStatus.OK
        data = response.json()
        assert data["upload_state"] == "queued"
        assert data["upload_attempt_id"] == "att-1"

    @patch("modules.publishing.submission.is_upload_active", return_value=False)
    async def test_status_job_missing_reports_failed(
        self,
        mock_active: MagicMock,
        client: AsyncClient,
        db_session: Session,
        tmp_path: Path,
        seed_experiment: SeedExperiment,
    ) -> None:
        """PVC says running but Job is gone → failed with job_missing reason."""
        from modules.publishing.status import UploadState, UploadStatus, write_status

        await seed_experiment("pstat", name="Status Test")
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

    @patch("modules.publishing.submission.is_upload_active", return_value=True)
    @patch("modules.publishing.submission.read_status")
    async def test_delete_blocked_during_active_upload(
        self, mock_read: MagicMock, mock_active: MagicMock, client: AsyncClient, db_session: Session, tmp_path: Path
    ) -> None:
        """Cannot delete an experiment with an active upload."""
        from modules.publishing.status import UploadState

        mock_read.return_value = MagicMock(state=UploadState.RUNNING.value, attempt_id="att-1")

        (tmp_path / "delup").mkdir(parents=True, exist_ok=True)
        exp = Experiment(id="delup", name="Upload Active")
        db_session.add(exp)
        await db_session.flush()
        nb = Notebook()
        nb.experiment_id = "delup"
        db_session.add(nb)
        await db_session.commit()

        response = await client.delete("/dash/api/experiments/delup")

        assert response.status_code == HTTPStatus.CONFLICT
