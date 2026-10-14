"""
Shared fixtures for dashboard API tests.

Every test gets its own DATA_DIR and SQLite file, an ASGI client, respx-mocked
HTTP (unmocked upstream calls fail loudly), and AsyncMock Kubernetes clients.
"""

import os
import sys
import tempfile
from collections.abc import AsyncIterator, Iterator
from datetime import UTC, datetime
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

import cache
import db
from app import create_app
from clients import http as http_client
from clients import k8s
from fastapi import FastAPI
from sqlalchemy.ext.asyncio import AsyncSession

# Modules binding DATA_DIR at import (`from config import DATA_DIR`).
_DATA_DIR_MODULES = (
    "config",
    "models.experiment",
    "models.experiment_sources",
    "models.simulation",
    "models.analysis_job",
    "models.gromacs_job",
    "models.amber_job",
    "routes.files",
    "routes.misc",
    "app",
)


@pytest.fixture(autouse=True)
def data_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Point every DATA_DIR binding at the test's tmp_path."""
    for name in _DATA_DIR_MODULES:
        module = sys.modules.get(name)
        if isinstance(module, ModuleType) and hasattr(module, "DATA_DIR"):
            monkeypatch.setattr(module, "DATA_DIR", tmp_path)
    return tmp_path


@pytest.fixture(autouse=True)
def _clear_caches() -> Iterator[None]:
    caches = (
        cache.mdrepo_status_cache,
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


def _running_pod() -> MagicMock:
    # Plausible pod shape: default MagicMock attributes produce truthy
    # deletion_timestamps and non-datetime start_times that break serialization.
    pod = MagicMock()
    pod.metadata.deletion_timestamp = None
    pod.status.phase = "Running"
    pod.status.container_statuses = []
    pod.status.start_time = datetime(2026, 1, 1, 12, 0, tzinfo=UTC)
    return pod


@pytest.fixture(autouse=True)
def mock_k8s() -> Iterator[tuple[AsyncMock, AsyncMock]]:
    """AsyncMock CoreV1Api/BatchV1Api clients; tests configure return values per call."""
    k8s.reset_k8s_clients_for_tests()
    k8s._load_k8s()
    core_v1, batch_v1 = AsyncMock(), AsyncMock()
    core_v1.read_namespaced_pod.return_value = _running_pod()
    core_v1.list_namespaced_pod.return_value = MagicMock(items=[])
    k8s._core_v1, k8s._batch_v1 = core_v1, batch_v1
    yield core_v1, batch_v1
    k8s.reset_k8s_clients_for_tests()


@pytest.fixture(autouse=True)
def http_mock() -> Iterator[respx.MockRouter]:
    """Mock all outgoing HTTP; a request without a matching route fails like an unreachable upstream."""
    with respx.mock(assert_all_called=False) as router:
        resolve = router.aresolve

        async def unreachable_unless_mocked(request: httpx.Request) -> object:
            try:
                return await resolve(request)
            except respx.models.AllMockedAssertionError as e:
                raise httpx.ConnectError(str(e), request=request) from e

        router.aresolve = unreachable_unless_mocked  # ty: ignore[invalid-assignment]
        yield router


@pytest.fixture
async def db_session(tmp_path: Path) -> AsyncIterator[AsyncSession]:
    """Provide a session on the test's own database; requests use separate sessions on the same file."""
    engine = db.init_engine(tmp_path / "test.db")
    async with engine.begin() as conn:
        await conn.run_sync(db.Base.metadata.create_all)
    async with db.session_factory()() as session:
        yield session
    await http_client.aclose()
    await engine.dispose()


@pytest.fixture
def app(db_session: AsyncSession) -> FastAPI:
    """Build the real application bound to the test database (lifespan startup is not run)."""
    return create_app()


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
