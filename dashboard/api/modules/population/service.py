"""
Datahugger-NG population: provisional Experiment submission, worker monitoring, and cancellation.

The worker writes only staged files and an atomic receipt. This module owns every database
write: the provisional Experiment and Notebook exist before the worker runs, the monitor
persists measured progress, finalization performs only the safe merge, and cancellation
confirms the worker is gone before committing a durable cancelled state.
"""

import asyncio
import logging
import secrets
import weakref
from datetime import UTC, datetime
from http import HTTPStatus
from pathlib import Path
from shutil import rmtree

import anyio
from clients import Clients
from core.config import DATA_DIR
from core.db import session_factory
from core.dependencies import ClientsDep, SessionDep
from core.enums import Engine, JobStatus, PopulationPhase, PopulationStatus, SourceType
from core.errors import ApiError, Conflict, NotFound
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from modules.experiments.models import Experiment
from modules.notebooks.models import Notebook
from modules.population.merge import PopulationMergeError, merge_staged
from modules.population.models import PopulationOperation
from modules.population.receipt import PopulationReceipt, operation_dir, read_receipt, staging_dir
from modules.population.submission import SubmissionError, delete_population_resources, job_name, submit_population_job

logger = logging.getLogger(__name__)

POPULATION_MONITOR_INTERVAL_SECONDS = 5

# Stable, user-safe failure texts; raw native details remain in server logs.
ERROR_SUBMISSION_FAILED = "The repository download could not be started."
ERROR_WORKER_FAILED = (
    "The repository download worker stopped without reporting a result. "
    "Contact support; they can inspect the short-term worker logs for this operation."
)
ERROR_WORKER_VANISHED = (
    "The repository download worker is no longer available and did not report a result. "
    "Try again or contact support if the failure persists."
)
ERROR_WORKER_EXITED = (
    "The repository download worker exited without reporting a successful download. "
    "Contact support; they can inspect the short-term worker logs for this operation."
)
ERROR_MERGE_FAILED = "The repository content could not be merged into the experiment."
ERROR_CANCELLATION_INCOMPLETE = "The repository download could not be cancelled yet. Try the cancellation again."
ERROR_TERMINAL_CANCELLATION = "The repository download is already finished and cannot be cancelled."

# One lock per event loop: serializes submission, cancellation, and reconciliation in this
# process so terminal states cannot race a late worker receipt.
_LIFECYCLE_LOCKS: weakref.WeakKeyDictionary[asyncio.AbstractEventLoop, asyncio.Lock] = weakref.WeakKeyDictionary()


def _lifecycle_lock() -> asyncio.Lock:
    loop = asyncio.get_running_loop()
    lock = _LIFECYCLE_LOCKS.get(loop)
    if lock is None:
        lock = asyncio.Lock()
        _LIFECYCLE_LOCKS[loop] = lock
    return lock


class PopulationService:
    """Population submission and cancellation on the request's session."""

    def __init__(self, session: SessionDep, clients: ClientsDep) -> None:
        """Bind to the request session and the upstream clients."""
        self._session = session
        self._clients = clients

    async def submit(
        self,
        *,
        experiment_id: str,
        name: str,
        repo_url: str,
        notebooks_repo: str | None,
        engine: Engine,
        module_name: str | None,
        module_category: str | None,
    ) -> PopulationOperation:
        """
        Commit a provisional Experiment together with its queued population and worker Job.

        Raises:
            ApiError: If the worker Job cannot be submitted or admitted (upstream-unavailable).
        """
        operation_id = secrets.token_hex(8)
        operation = PopulationOperation(
            id=operation_id,
            experiment_id=experiment_id,
            name=name,
            repo_url=repo_url,
            notebooks_repo=notebooks_repo,
            engine=engine,
            module_name=module_name,
            module_category=module_category,
            job_name=job_name(operation_id),
            status=PopulationStatus.queued,
            phase=PopulationPhase.starting,
        )
        experiment = Experiment(
            id=experiment_id,
            name=name,
            source_type=SourceType.REPO,
            source_ref=repo_url,
            notebooks_repo=notebooks_repo,
            engine=engine,
            module_name=module_name,
            module_category=module_category,
            notebook=Notebook(experiment_id=experiment_id),
            tuner_jobs=[],
            simulation_jobs=[],
            analysis_jobs=[],
            population=operation,
        )

        async with _lifecycle_lock():
            self._session.add(experiment)
            try:
                await submit_population_job(self._clients.k8s, operation)
            except SubmissionError:
                await self._session.rollback()
                _cleanup(operation, remove_experiment_dir=True)
                raise ApiError(
                    HTTPStatus.INTERNAL_SERVER_ERROR,
                    ERROR_SUBMISSION_FAILED,
                    "urn:mddash:upstream-unavailable",
                    "The download worker could not be started; check the service and try again.",
                )
            try:
                await self._session.commit()
            except BaseException:
                # The admitted Job must not survive a non-durable provisional row.
                try:
                    await delete_population_resources(self._clients.k8s, operation)
                except Exception:
                    logger.exception("Could not delete population Job %s after a failed commit", operation.job_name)
                await self._session.rollback()
                _cleanup(operation, remove_experiment_dir=True)
                raise
        logger.info("Population %s submitted for experiment %s", operation.id, experiment_id)
        return operation

    async def cancel(self, experiment: Experiment) -> PopulationOperation:
        """
        Cancel an active population after its worker is confirmed gone.

        Raises:
            NotFound: If the experiment has no population operation.
            Conflict: If the operation is already terminal.
            ApiError: If the worker cannot be confirmed deleted (state remains ``cancelling``).
        """
        operation = experiment.population
        if operation is None:
            raise NotFound(f"Experiment {experiment.id} has no Datahugger population")

        async with _lifecycle_lock():
            operation = await self._session.get(PopulationOperation, operation.id, populate_existing=True)
            if operation is None:
                raise NotFound(f"Population operation {experiment.id} not found")
            if operation.status not in PopulationStatus.cancellable():
                raise Conflict(ERROR_TERMINAL_CANCELLATION)

            operation.status = PopulationStatus.cancelling
            operation.phase = PopulationPhase.cancelling
            await self._session.commit()

            try:
                gone = await delete_population_resources(self._clients.k8s, operation)
            except Exception:
                logger.exception("Population %s cancellation deletion failed", operation.id)
                operation.error = ERROR_CANCELLATION_INCOMPLETE
                await self._session.commit()
                raise ApiError(
                    HTTPStatus.INTERNAL_SERVER_ERROR,
                    ERROR_CANCELLATION_INCOMPLETE,
                    "urn:mddash:upstream-unavailable",
                    "The download worker could not be stopped yet; try the cancellation again.",
                )
            if not gone:
                operation.error = ERROR_CANCELLATION_INCOMPLETE
                await self._session.commit()
                raise ApiError(
                    HTTPStatus.INTERNAL_SERVER_ERROR,
                    ERROR_CANCELLATION_INCOMPLETE,
                    "urn:mddash:upstream-unavailable",
                    "The download worker could not be stopped yet; try the cancellation again.",
                )

            await anyio.to_thread.run_sync(lambda: _cleanup(operation, remove_experiment_dir=True))
            operation.status = PopulationStatus.cancelled
            operation.error = None
            operation.finished_at = datetime.now(UTC)
            await self._session.commit()
            logger.info("Population %s cancelled for experiment %s", operation.id, experiment.id)
            return operation


async def run_population_monitor(clients: Clients) -> None:
    """App-lifespan reconciliation: population completes without a polling browser session."""
    while True:
        await asyncio.sleep(POPULATION_MONITOR_INTERVAL_SECONDS)
        try:
            await _reconcile_tick(clients)
        except Exception:
            logger.exception("Population monitor tick failed")


async def _reconcile_tick(clients: Clients) -> None:
    """Reconcile every active operation with a fresh session (read-only status GETs never do this)."""
    async with _lifecycle_lock(), session_factory()() as session:
        operations = (
            (
                await session.execute(
                    select(PopulationOperation).where(PopulationOperation.status.in_(list(PopulationStatus.active())))
                )
            )
            .scalars()
            .all()
        )
        for operation in operations:
            try:
                await _reconcile(session, clients, operation)
                await session.commit()
            except Exception:
                logger.exception("Population %s reconciliation failed", operation.id)
                await session.rollback()


async def _reconcile(session: AsyncSession, clients: Clients, operation: PopulationOperation) -> None:
    """
    Drive one active operation to a terminal state from worker state and its receipt.

    A Kubernetes read error raises, so the tick skips the operation instead of failing it.
    """
    # Job before receipt: a worker that writes its receipt and exits between the reads is a success, not an exit.
    state = await clients.k8s.read_job_status(operation.job_name)
    receipt = await anyio.to_thread.run_sync(read_receipt, operation.id)
    if receipt is not None and receipt.state == PopulationStatus.succeeded.value:
        resumed = operation.phase is PopulationPhase.finalizing
        _apply_progress(operation, receipt)
        # Finalize only after the worker completed (or TTL-expired), never while it still runs.
        if not await _worker_active(clients, operation.job_name):
            operation.phase = PopulationPhase.finalizing
            await session.commit()
            await _finalize(session, operation, resumed=resumed)
        return
    if receipt is not None and receipt.state == PopulationStatus.failed.value:
        _apply_progress(operation, receipt)
        await _fail(session, operation, receipt.error or ERROR_WORKER_FAILED)
        return

    if state in {JobStatus.ERROR, JobStatus.FINISHED}:
        # No usable receipt: preserve raw pod evidence only in server logs before the finite job TTL.
        logs = await clients.k8s.get_job_logs(operation.job_name)
        if logs:
            logger.error("Population %s failed worker %s logs:\n%s", operation.id, operation.job_name, logs)
        if state is JobStatus.FINISHED:
            # The worker exited without a valid success receipt.
            await _fail(session, operation, ERROR_WORKER_EXITED)
        elif state is JobStatus.ERROR:
            # Failed or deadlined without a valid success receipt.
            await _fail(session, operation, ERROR_WORKER_FAILED)
    elif state is JobStatus.UNKNOWN:
        await _fail(session, operation, ERROR_WORKER_VANISHED)
    else:
        _apply_progress(operation, receipt)
        if operation.status is PopulationStatus.queued:
            operation.status = PopulationStatus.running
            await session.commit()


async def _worker_active(clients: Clients, job_name_: str) -> bool:
    """Whether the population Job still has an active pod."""
    job = await clients.k8s.read_job(job_name_)
    status = getattr(job, "status", None)
    active = getattr(status, "active", 0) if status is not None else 0
    return (active or 0) > 0


def _apply_progress(operation: PopulationOperation, receipt: PopulationReceipt | None) -> None:
    """Copy the latest bounded receipt progress onto the operation (never infer completion from bytes)."""
    if receipt is None:
        return
    if receipt.phase in PopulationPhase._value2member_map_:
        operation.phase = PopulationPhase(receipt.phase)
    operation.files_present = max(0, int(receipt.files_present or 0))
    operation.files_total = receipt.files_total
    operation.bytes_present = max(0, int(receipt.bytes_present or 0))
    operation.bytes_total = receipt.bytes_total


async def _finalize(session: AsyncSession, operation: PopulationOperation, *, resumed: bool) -> None:
    """Merge the staged dataset into the existing provisional Experiment and mark it succeeded."""
    experiment_dir = DATA_DIR / operation.experiment_id
    staged = staging_dir(operation.id)
    try:
        # An interrupted finalization may have moved everything already; an empty staging dir is then done.
        if not (resumed and _is_empty(staged)):
            renamed = await anyio.to_thread.run_sync(merge_staged, staged, experiment_dir)
            operation.renamed_paths = renamed or None
    except (PopulationMergeError, OSError) as e:
        logger.error("Population %s merge failed: %s", operation.id, e)
        await _fail(session, operation, ERROR_MERGE_FAILED, remove_experiment_dir=True)
        return

    operation.status = PopulationStatus.succeeded
    operation.finished_at = datetime.now(UTC)
    await session.commit()
    # Successful temporary artifacts are removed after atomic completion.
    await anyio.to_thread.run_sync(lambda: _cleanup(operation))
    logger.info("Population %s finalized experiment %s", operation.id, operation.experiment_id)


async def _fail(
    session: AsyncSession, operation: PopulationOperation, error: str, *, remove_experiment_dir: bool = True
) -> None:
    """Preserve the provisional Experiment and latest progress while removing partial data."""
    await anyio.to_thread.run_sync(lambda: _cleanup(operation, remove_experiment_dir=remove_experiment_dir))
    operation.status = PopulationStatus.failed
    operation.error = error
    operation.finished_at = datetime.now(UTC)
    await session.commit()
    logger.warning("Population %s failed: %s", operation.id, error)


def _is_empty(path: Path) -> bool:
    return not path.is_dir() or not any(path.iterdir())


def _cleanup(operation: PopulationOperation, *, remove_experiment_dir: bool = False) -> None:
    """Best-effort removal of the operation's staging root (and the prepared experiment dir)."""
    rmtree(operation_dir(operation.id), ignore_errors=True)
    if remove_experiment_dir:
        rmtree(DATA_DIR / operation.experiment_id, ignore_errors=True)
