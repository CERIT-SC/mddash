"""Unit tests for the population monitor: worker/receipt reconciliation and finalization."""

from collections.abc import AsyncIterator
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from clients import Clients
from core.enums import Engine, JobStatus, PopulationStatus, SourceType
from modules.models import Experiment, Notebook
from modules.population.models import PopulationOperation
from modules.population.receipt import staging_dir, write_receipt
from modules.population.service import ERROR_MERGE_FAILED, ERROR_WORKER_FAILED, _reconcile_tick
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession as Session

OPERATION_ID = "0123456789abcdef"
EXPERIMENT_ID = "abcde"
REPO_URL = "https://github.com/test/dataset"


@pytest.fixture
async def population_clients() -> AsyncIterator[tuple[Clients, AsyncMock]]:
    """Build a clients bundle over a bare AsyncMock Kubernetes client (worker state is scripted per test)."""
    k8s = AsyncMock()
    bundle = Clients.create(k8s=k8s)
    yield bundle, k8s
    await bundle.http.aclose()


async def _seed_operation(
    db_session: Session, tmp_path: Path, *, status: PopulationStatus = PopulationStatus.queued
) -> None:
    """Commit an active operation with its prepared (notebook-only) experiment directory."""
    operation = PopulationOperation(
        id=OPERATION_ID,
        experiment_id=EXPERIMENT_ID,
        name="Datahugger Experiment",
        repo_url=REPO_URL,
        engine=Engine.GMX,
        job_name="datahugger-populate-0123456789abcdef",
        status=status,
    )
    db_session.add(operation)
    await db_session.commit()

    experiment_dir = tmp_path / EXPERIMENT_ID
    experiment_dir.mkdir(parents=True, exist_ok=True)
    (experiment_dir / "notebooks.ipynb").write_text("nb")


async def _operation(db_session: Session) -> PopulationOperation:
    operation = await db_session.get(PopulationOperation, OPERATION_ID, populate_existing=True)
    assert operation is not None
    return operation


async def _experiments(db_session: Session) -> list[Experiment]:
    return list((await db_session.execute(select(Experiment))).scalars().all())


class TestReconcile:
    """Active operations are driven to a terminal state from the receipt and the worker Job."""

    async def test_success_receipt_finalizes_experiment(
        self, db_session: Session, tmp_path, population_clients: tuple[Clients, AsyncMock]
    ) -> None:
        """A success receipt with a completed worker merges the dataset and creates the experiment."""
        bundle, k8s = population_clients
        await _seed_operation(db_session, tmp_path)
        staging = staging_dir(OPERATION_ID)
        (staging / "files").mkdir(parents=True)
        (staging / "files" / "data.pdb").write_text("A")
        write_receipt(OPERATION_ID, "succeeded")
        k8s.read_job.return_value = None  # worker gone (finished / TTL-expired)

        await _reconcile_tick(bundle)

        operation = await _operation(db_session)
        assert operation.status is PopulationStatus.succeeded
        assert operation.finished_at is not None
        assert operation.error is None

        experiment = (await _experiments(db_session))[0]
        assert experiment.id == EXPERIMENT_ID
        assert experiment.name == "Datahugger Experiment"
        assert experiment.source_type is SourceType.REPO
        assert experiment.source_ref == REPO_URL
        assert (await db_session.execute(select(Notebook))).scalars().one().experiment_id == EXPERIMENT_ID

        # Staged content merged at the experiment root, beside the prepared notebooks.
        assert (tmp_path / EXPERIMENT_ID / "files" / "data.pdb").read_text() == "A"
        assert (tmp_path / EXPERIMENT_ID / "notebooks.ipynb").read_text() == "nb"

        # Successful temporary artifacts are removed after atomic completion.
        assert not staging.exists()

    async def test_success_receipt_held_while_worker_active(
        self, db_session: Session, tmp_path, population_clients: tuple[Clients, AsyncMock]
    ) -> None:
        """A success receipt is never finalized while the worker Job still has an active pod."""
        bundle, k8s = population_clients
        await _seed_operation(db_session, tmp_path)
        staging = staging_dir(OPERATION_ID)
        (staging / "files").mkdir(parents=True)
        (staging / "files" / "data.pdb").write_text("A")
        write_receipt(OPERATION_ID, "succeeded")
        k8s.read_job.return_value = SimpleNamespace(status=SimpleNamespace(active=1))

        await _reconcile_tick(bundle)

        operation = await _operation(db_session)
        assert operation.status is PopulationStatus.queued
        assert await _experiments(db_session) == []
        assert (staging / "files" / "data.pdb").is_file()

    async def test_failed_receipt_fails_operation_and_cleans_up(
        self, db_session: Session, tmp_path, population_clients: tuple[Clients, AsyncMock]
    ) -> None:
        """A failed receipt becomes a durable failure; prepared and staged content is removed."""
        bundle, k8s = population_clients
        await _seed_operation(db_session, tmp_path)
        staging = staging_dir(OPERATION_ID)
        (staging / "files").mkdir(parents=True)
        (staging / "files" / "partial.pdb").write_text("x")
        write_receipt(OPERATION_ID, "failed", "The repository download failed.")
        k8s.read_job.return_value = None

        await _reconcile_tick(bundle)

        operation = await _operation(db_session)
        assert operation.status is PopulationStatus.failed
        assert operation.error == "The repository download failed."
        assert operation.finished_at is not None
        assert await _experiments(db_session) == []
        assert not staging.exists()
        assert not (tmp_path / EXPERIMENT_ID).exists()

    @pytest.mark.parametrize(
        "job_status",
        [JobStatus.FINISHED, JobStatus.ERROR, JobStatus.UNKNOWN],
        ids=["finished-without-receipt", "error", "vanished"],
    )
    async def test_dead_worker_without_receipt_fails(
        self, db_session: Session, tmp_path, population_clients: tuple[Clients, AsyncMock], job_status: JobStatus
    ) -> None:
        """A finished, errored, or vanished worker without a valid success receipt is a durable failure."""
        bundle, k8s = population_clients
        await _seed_operation(db_session, tmp_path)
        k8s.get_job_status.return_value = job_status

        await _reconcile_tick(bundle)

        operation = await _operation(db_session)
        assert operation.status is PopulationStatus.failed
        assert operation.error == ERROR_WORKER_FAILED
        assert await _experiments(db_session) == []
        assert not (tmp_path / EXPERIMENT_ID).exists()

    async def test_live_worker_marks_operation_running(
        self, db_session: Session, tmp_path, population_clients: tuple[Clients, AsyncMock]
    ) -> None:
        """A still-running worker with no receipt advances the operation to running."""
        bundle, k8s = population_clients
        await _seed_operation(db_session, tmp_path)
        k8s.get_job_status.return_value = JobStatus.RUNNING

        await _reconcile_tick(bundle)

        operation = await _operation(db_session)
        assert operation.status is PopulationStatus.running
        assert operation.error is None
        assert await _experiments(db_session) == []

    async def test_merge_failure_fails_operation_and_cleans_up(
        self, db_session: Session, tmp_path, population_clients: tuple[Clients, AsyncMock]
    ) -> None:
        """Unsafe staged content fails finalization; no experiment, and the prepared dir is removed."""
        bundle, k8s = population_clients
        await _seed_operation(db_session, tmp_path)
        staging = staging_dir(OPERATION_ID)
        (staging / "sub").mkdir(parents=True)
        (staging / "sub" / "link").symlink_to("/etc/passwd")
        write_receipt(OPERATION_ID, "succeeded")
        k8s.read_job.return_value = None

        await _reconcile_tick(bundle)

        operation = await _operation(db_session)
        assert operation.status is PopulationStatus.failed
        assert operation.error == ERROR_MERGE_FAILED
        assert await _experiments(db_session) == []
        assert not (tmp_path / EXPERIMENT_ID).exists()
        assert not staging.exists()

    async def test_multiple_operations_reconciled_independently(
        self, db_session: Session, tmp_path, population_clients: tuple[Clients, AsyncMock]
    ) -> None:
        """One failing operation never blocks another from finalizing."""
        bundle, k8s = population_clients
        await _seed_operation(db_session, tmp_path)
        other = PopulationOperation(
            id="fedcba9876543210",
            experiment_id="efghi",
            name="Other",
            repo_url=REPO_URL,
            engine=Engine.GMX,
            job_name="datahugger-populate-fedcba9876543210",
            status=PopulationStatus.queued,
        )
        db_session.add(other)
        await db_session.commit()
        (tmp_path / "efghi").mkdir(parents=True)

        other_staging = staging_dir("fedcba9876543210")
        (other_staging / "data.txt").parent.mkdir(parents=True)
        (other_staging / "data.txt").write_text("B")
        write_receipt("fedcba9876543210", "succeeded")

        k8s.get_job_status.return_value = JobStatus.ERROR  # the first operation's worker died
        k8s.read_job.return_value = None

        await _reconcile_tick(bundle)

        first = await _operation(db_session)
        assert first.status is PopulationStatus.failed
        second = await db_session.get(PopulationOperation, "fedcba9876543210", populate_existing=True)
        assert second is not None
        assert second.status is PopulationStatus.succeeded
        assert (tmp_path / "efghi" / "data.txt").read_text() == "B"
        assert len(await _experiments(db_session)) == 1
