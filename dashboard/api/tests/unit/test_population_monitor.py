"""Unit tests for the population monitor: worker/receipt reconciliation and finalization."""

from collections.abc import AsyncIterator
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from clients import Clients
from core.enums import Engine, JobStatus, PopulationPhase, PopulationStatus, SourceType
from modules.models import Experiment, Notebook
from modules.population.models import PopulationOperation
from modules.population.receipt import staging_dir, write_receipt
from modules.population.service import (
    ERROR_MERGE_FAILED,
    ERROR_WORKER_EXITED,
    ERROR_WORKER_FAILED,
    ERROR_WORKER_VANISHED,
    _reconcile_tick,
)
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
    db_session: Session,
    tmp_path: Path,
    *,
    status: PopulationStatus = PopulationStatus.queued,
    operation_id: str = OPERATION_ID,
    experiment_id: str = EXPERIMENT_ID,
    name: str = "Datahugger Experiment",
) -> None:
    """Commit the provisional experiment together with its population (as submission does)."""
    operation = PopulationOperation(
        id=operation_id,
        experiment_id=experiment_id,
        name=name,
        repo_url=REPO_URL,
        engine=Engine.GMX,
        job_name=f"datahugger-populate-{operation_id}",
        status=status,
    )
    experiment = Experiment(
        id=experiment_id,
        name=name,
        source_type=SourceType.REPO,
        source_ref=REPO_URL,
        engine=Engine.GMX,
        notebook=Notebook(experiment_id=experiment_id),
        tuner_jobs=[],
        simulation_jobs=[],
        analysis_jobs=[],
        population=operation,
    )
    db_session.add(experiment)
    await db_session.commit()

    experiment_dir = tmp_path / experiment_id
    experiment_dir.mkdir(parents=True, exist_ok=True)
    (experiment_dir / "notebooks.ipynb").write_text("nb")


async def _operation(db_session: Session, operation_id: str = OPERATION_ID) -> PopulationOperation:
    operation = await db_session.get(PopulationOperation, operation_id, populate_existing=True)
    assert operation is not None
    return operation


async def _experiments(db_session: Session) -> list[Experiment]:
    return list((await db_session.execute(select(Experiment))).scalars().all())


class TestReconcile:
    """Active operations are driven to a terminal state from the receipt and the worker Job."""

    @pytest.mark.parametrize(
        "job",
        [
            None,
            SimpleNamespace(status=SimpleNamespace(active=None)),
            SimpleNamespace(status=SimpleNamespace(active=0)),
        ],
        ids=["deleted", "inactive-null", "inactive-zero"],
    )
    async def test_success_receipt_finalizes_experiment(
        self,
        db_session: Session,
        tmp_path,
        population_clients: tuple[Clients, AsyncMock],
        job: object,
    ) -> None:
        """A success receipt with a completed worker merges the dataset into the provisional experiment."""
        bundle, k8s = population_clients
        await _seed_operation(db_session, tmp_path)
        staging = staging_dir(OPERATION_ID)
        (staging / "files").mkdir(parents=True)
        (staging / "files" / "data.pdb").write_text("A")
        write_receipt(OPERATION_ID, "succeeded")
        k8s.read_job.return_value = job  # completed Jobs may report active=None or disappear on TTL expiry

        await _reconcile_tick(bundle)

        operation = await _operation(db_session)
        assert operation.status is PopulationStatus.succeeded
        assert operation.finished_at is not None
        assert operation.error is None

        # The provisional experiment created at submission is the final one: it is never recreated.
        experiment = (await _experiments(db_session))[0]
        assert experiment.id == EXPERIMENT_ID
        assert experiment.name == "Datahugger Experiment"
        assert experiment.source_type is SourceType.REPO
        assert experiment.source_ref == REPO_URL
        assert experiment.population is operation
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
        # The provisional experiment stays visible (and unfinished) the whole time.
        experiment = (await _experiments(db_session))[0]
        assert experiment.population is not None
        assert experiment.population.status is PopulationStatus.queued
        assert (staging / "files" / "data.pdb").is_file()

    async def test_receipt_progress_is_persisted_on_active_reconciliation(
        self, db_session: Session, tmp_path, population_clients: tuple[Clients, AsyncMock]
    ) -> None:
        """Measured progress from a running receipt lands on the operation without finalizing it."""
        bundle, k8s = population_clients
        await _seed_operation(db_session, tmp_path)
        write_receipt(
            OPERATION_ID,
            "running",
            phase="downloading",
            files_present=3,
            files_total=10,
            bytes_present=30,
            bytes_total=100,
        )
        k8s.get_job_status.return_value = JobStatus.RUNNING

        await _reconcile_tick(bundle)

        operation = await _operation(db_session)
        assert operation.status is PopulationStatus.running
        assert operation.phase is PopulationPhase.downloading
        assert operation.files_present == 3
        assert operation.files_total == 10
        assert operation.bytes_present == 30
        assert operation.bytes_total == 100
        assert (await _experiments(db_session))[0].population is operation

    async def test_cancelling_operations_are_untouched_by_monitor(
        self, db_session: Session, tmp_path, population_clients: tuple[Clients, AsyncMock]
    ) -> None:
        """The monitor only reconciles queued/running; a cancelling operation can never be overwritten."""
        bundle, k8s = population_clients
        await _seed_operation(db_session, tmp_path, status=PopulationStatus.cancelling)
        # A late success receipt must not race the in-flight cancellation.
        staging = staging_dir(OPERATION_ID)
        (staging / "data.pdb").parent.mkdir(parents=True)
        (staging / "data.pdb").write_text("A")
        write_receipt(OPERATION_ID, "succeeded")

        await _reconcile_tick(bundle)

        operation = await _operation(db_session)
        assert operation.status is PopulationStatus.cancelling
        k8s.read_job.assert_not_awaited()
        k8s.get_job_status.assert_not_awaited()
        cancelling = (await _experiments(db_session))[0].population
        assert cancelling is not None
        assert cancelling.status is PopulationStatus.cancelling

    async def test_failed_receipt_fails_operation_and_keeps_experiment(
        self, db_session: Session, tmp_path, population_clients: tuple[Clients, AsyncMock]
    ) -> None:
        """A failed receipt becomes a durable failure; the provisional experiment and its error persist."""
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
        # The failed experiment stays visible for inspection until explicit deletion.
        experiment = (await _experiments(db_session))[0]
        assert experiment.population is not None
        assert experiment.population.status is PopulationStatus.failed
        assert experiment.population.error == "The repository download failed."
        assert not staging.exists()
        assert not (tmp_path / EXPERIMENT_ID).exists()

    @pytest.mark.parametrize(
        ("job_status", "expected"),
        [
            (JobStatus.FINISHED, ERROR_WORKER_EXITED),
            (JobStatus.ERROR, ERROR_WORKER_FAILED),
            (JobStatus.UNKNOWN, ERROR_WORKER_VANISHED),
        ],
        ids=["finished-without-receipt", "error", "vanished"],
    )
    async def test_dead_worker_without_receipt_fails(
        self,
        db_session: Session,
        tmp_path,
        population_clients: tuple[Clients, AsyncMock],
        job_status: JobStatus,
        expected: str,
    ) -> None:
        """A finished, errored, or vanished worker without a success receipt explains its distinct state."""
        bundle, k8s = population_clients
        await _seed_operation(db_session, tmp_path)
        k8s.get_job_status.return_value = job_status
        k8s.get_job_logs.return_value = "Traceback: native secret details"

        await _reconcile_tick(bundle)

        operation = await _operation(db_session)
        assert operation.status is PopulationStatus.failed
        assert operation.error == expected
        assert "native" not in operation.error
        failed = (await _experiments(db_session))[0].population
        assert failed is not None
        assert failed.status is PopulationStatus.failed
        assert not (tmp_path / EXPERIMENT_ID).exists()
        if job_status is JobStatus.UNKNOWN:
            k8s.get_job_logs.assert_not_awaited()
        else:
            k8s.get_job_logs.assert_awaited_once_with(operation.job_name)

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
        running = (await _experiments(db_session))[0].population
        assert running is not None
        assert running.status is PopulationStatus.running

    async def test_merge_failure_fails_operation_and_keeps_experiment(
        self, db_session: Session, tmp_path, population_clients: tuple[Clients, AsyncMock]
    ) -> None:
        """Unsafe staged content fails finalization; the provisional experiment is kept with the error."""
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
        failed = (await _experiments(db_session))[0].population
        assert failed is not None
        assert failed.status is PopulationStatus.failed
        assert not (tmp_path / EXPERIMENT_ID).exists()
        assert not staging.exists()

    async def test_multiple_operations_reconciled_independently(
        self, db_session: Session, tmp_path, population_clients: tuple[Clients, AsyncMock]
    ) -> None:
        """One failing operation never blocks another from finalizing."""
        bundle, k8s = population_clients
        await _seed_operation(db_session, tmp_path)
        await _seed_operation(
            db_session,
            tmp_path,
            operation_id="fedcba9876543210",
            experiment_id="efghi",
            name="Other",
        )
        (staging_dir("fedcba9876543210") / "data.txt").parent.mkdir(parents=True)
        (staging_dir("fedcba9876543210") / "data.txt").write_text("B")
        write_receipt("fedcba9876543210", "succeeded")

        k8s.get_job_status.return_value = JobStatus.ERROR  # the first operation's worker died
        k8s.read_job.return_value = None

        await _reconcile_tick(bundle)

        first = await _operation(db_session)
        assert first.status is PopulationStatus.failed
        second = await _operation(db_session, "fedcba9876543210")
        assert second.status is PopulationStatus.succeeded
        assert (tmp_path / "efghi" / "data.txt").read_text() == "B"
        # Both provisional experiments survive: the failed one for inspection, the succeeded one usable.
        experiments = await _experiments(db_session)
        assert {e.id: (e.population.status if e.population is not None else None) for e in experiments} == {
            EXPERIMENT_ID: PopulationStatus.failed,
            "efghi": PopulationStatus.succeeded,
        }
