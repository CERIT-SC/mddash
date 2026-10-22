"""
Shared fixtures for dashboard API tests.

Every test gets its own DATA_DIR and SQLite file, an ASGI client, respx-mocked
HTTP (unmocked upstream calls fail loudly), and AsyncMock Kubernetes clients.
"""

import os
import shutil
import sys
import tempfile
from collections.abc import AsyncIterator, Iterator
from pathlib import Path
from types import ModuleType
from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest
import respx

# Add parent directory to path so we can import app modules
sys.path.insert(0, str(Path(__file__).parent.parent))

# config.py reads these at import time.
os.environ["DATA_DIR"] = tempfile.mkdtemp(prefix="mddash_test_")
os.environ["JUPYTERHUB_USER"] = "testuser"
os.environ.pop("JUPYTERHUB_SERVICE_PREFIX", None)
os.environ["POD_NAMESPACE"] = "test-namespace"
os.environ["HUB_NAMESPACE"] = "test-hub-namespace"
os.environ["PVC_NAME"] = "test-pvc"
os.environ["PVC_STORAGE_SIZE"] = "1Gi"
os.environ["NS_MAX_NOTEBOOKS"] = "2"
os.environ["TUNER_USER"] = "tuner"
os.environ["TUNER_PASSWORD"] = "secret"

from app import create_app
from clients import Clients
from clients.k8s import K8sClient
from core import cache, db
from fastapi import FastAPI
from modules.models import Experiment, Notebook  # importing every model also binds every DATA_DIR
from sqlalchemy.ext.asyncio import AsyncSession
from tests.support import SeedExperiment, pod


@pytest.fixture(autouse=True)
def data_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Point every DATA_DIR binding (`from core.config import DATA_DIR`) at the test's tmp_path."""
    for name, module in list(sys.modules.items()):
        bound = name == "app" or name.startswith(("core.", "modules.", "_demo."))
        if bound and isinstance(module, ModuleType) and hasattr(module, "DATA_DIR"):
            monkeypatch.setattr(module, "DATA_DIR", tmp_path)
    return tmp_path


@pytest.fixture(autouse=True)
def _clear_caches() -> Iterator[None]:
    caches = (
        cache.mdrepo_status_cache,
        cache.mdrepo_spent_grants,
        cache.tuner_status_cache,
        cache.tuner_last_known_status,
        cache.analysis_status_cache,
        cache.simulation_status_cache,
        cache.simulation_log_lines_cache,
        cache.archive_status_cache,
    )
    for c in caches:
        c.clear()
    yield
    for c in caches:
        c.clear()


@pytest.fixture
def mock_k8s() -> tuple[AsyncMock, AsyncMock]:
    """AsyncMock CoreV1Api/BatchV1Api clients behind `clients.k8s`; tests configure return values per call."""
    core_v1, batch_v1 = AsyncMock(), AsyncMock()
    core_v1.read_namespaced_pod.return_value = pod()
    core_v1.list_namespaced_pod.return_value = MagicMock(items=[])
    return core_v1, batch_v1


@pytest.fixture
async def clients(mock_k8s: tuple[AsyncMock, AsyncMock]) -> AsyncIterator[Clients]:
    """Production clients over respx-mocked HTTP, with the AsyncMock Kubernetes API."""
    core_v1, batch_v1 = mock_k8s
    bundle = Clients.create(k8s=K8sClient(core_v1=core_v1, batch_v1=batch_v1))
    yield bundle
    await bundle.http.aclose()


@pytest.fixture(autouse=True)
def http_mock() -> Iterator[respx.MockRouter]:
    """Mock all outgoing HTTP; a request without a matching route fails like an unreachable upstream."""
    with respx.mock(assert_all_called=False) as router:
        resolve, aresolve = router.resolve, router.aresolve

        def unreachable_unless_mocked(request: httpx.Request) -> object:
            try:
                return resolve(request)
            except respx.models.AllMockedAssertionError as e:
                raise httpx.ConnectError(str(e), request=request) from e

        async def aunreachable_unless_mocked(request: httpx.Request) -> object:
            try:
                return await aresolve(request)
            except respx.models.AllMockedAssertionError as e:
                raise httpx.ConnectError(str(e), request=request) from e

        router.resolve = unreachable_unless_mocked  # ty: ignore[invalid-assignment]
        router.aresolve = aunreachable_unless_mocked  # ty: ignore[invalid-assignment]
        yield router


@pytest.fixture(scope="session")
def migrated_db(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """Build a database with the migrations, like production (once per worker; tests copy it)."""
    path = tmp_path_factory.mktemp("migrated") / "template.db"
    db.run_migrations(path)
    return path


@pytest.fixture
async def db_session(tmp_path: Path, migrated_db: Path) -> AsyncIterator[AsyncSession]:
    """Provide a session on the test's own database; requests use separate sessions on the same file."""
    path = tmp_path / "test.db"
    shutil.copyfile(migrated_db, path)
    engine = db.init_engine(path)
    async with db.session_factory()() as session:
        yield session
    await engine.dispose()


@pytest.fixture
def seed_experiment(db_session: AsyncSession, tmp_path: Path) -> SeedExperiment:
    """Persist an experiment with its notebook and create its directory; returns (id, directory)."""

    async def seed(exp_id: str = "simts", *, name: str = "Test experiment", **columns: object) -> tuple[str, Path]:
        columns.setdefault("notebooks_repo", "https://github.com/t/r.git")
        db_session.add(Experiment(id=exp_id, name=name, **columns))
        db_session.add(Notebook(experiment_id=exp_id))
        await db_session.commit()
        exp_dir = tmp_path / exp_id
        exp_dir.mkdir(parents=True, exist_ok=True)
        return exp_id, exp_dir

    return seed


@pytest.fixture
def app(db_session: AsyncSession, clients: Clients) -> FastAPI:
    """Build the real application bound to the test database and clients (lifespan startup is not run)."""
    return create_app(clients=clients)


@pytest.fixture
async def client(app: FastAPI) -> AsyncIterator[httpx.AsyncClient]:
    """ASGI client; https so the Secure session cookie round-trips."""
    transport = httpx.ASGITransport(app=app, raise_app_exceptions=False)
    async with httpx.AsyncClient(transport=transport, base_url="https://testserver") as c:
        yield c


@pytest.fixture
def sample_pdb_content() -> bytes:
    """Minimal valid PDB file content."""
    return b"""HEADER    TEST PROTEIN
ATOM      1  N   ALA A   1       0.000   0.000   0.000  1.00  0.00           N
ATOM      2  CA  ALA A   1       1.458   0.000   0.000  1.00  0.00           C
ATOM      3  C   ALA A   1       2.009   1.420   0.000  1.00  0.00           C
ATOM      4  O   ALA A   1       1.251   2.390   0.000  1.00  0.00           O
END
"""
