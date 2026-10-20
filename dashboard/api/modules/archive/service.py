"""Experiment archive/restore/purge: durable K8s Jobs reconciled with DB markers and the status doc."""

import logging
from datetime import UTC, datetime
from http import HTTPStatus
from typing import Annotated

import anyio
from core.cache import archive_status_cache
from core.config import DATA_DIR, S3_BUCKET
from core.dependencies import ClientsDep, SessionDep
from core.errors import ApiError
from fastapi import Depends

from modules.archive import submission
from modules.archive.status import ArchiveDirection, ArchiveState, read_status
from modules.experiments.models import Experiment
from modules.jobs.service import JobsService
from modules.notebooks.service import NotebookService
from modules.publishing.status import UploadState
from modules.publishing.submission import read_upload_state

logger = logging.getLogger(__name__)


def _s3_not_configured(action: str) -> ApiError:
    return ApiError(
        HTTPStatus.BAD_REQUEST,
        f"S3 storage is not configured on this deployment; {action} is unavailable.",
        "urn:mddash:s3-not-configured",
        "S3 storage isn't enabled on this deployment; contact the administrator.",
    )


class ArchiveService:
    """Archive state of experiments and the Jobs that move them to/from S3."""

    def __init__(self, session: SessionDep, clients: ClientsDep) -> None:
        """Bind to the request session, the Kubernetes client, and the job/notebook services."""
        self._session = session
        self._k8s = clients.k8s
        self._jobs = JobsService(session, clients)
        self._notebooks = NotebookService(clients)

    async def refresh_state(self, experiment: Experiment) -> str | None:
        """Reconcile and store the archive state; experiments without archive markers skip all I/O."""
        state = (
            None
            if experiment.archived_at is None and experiment.archived_step is None
            else await self._read_state(experiment)
        )
        experiment.record_archive_state(state)
        return state

    async def _is_job_live(self, direction: str, experiment_id: str) -> bool:
        """Job liveness with a short lookup cache (list serialization fan-out)."""
        key = (direction, experiment_id)
        if (cached := archive_status_cache.get(key)) is not None:
            return cached
        live = await submission.is_job_active(self._k8s, direction, experiment_id)
        archive_status_cache[key] = live
        return live

    async def _read_state(self, experiment: Experiment) -> str | None:
        """
        Reconcile archive state from DB markers, the status doc, and live Jobs.

        DB markers are durable (snapshots = submitted, archived_at = completed); the
        doc dies with the dir and Jobs TTL-expire, so completion is inferred. An
        in-flight doc with no live Job failed. Mutates the row only on terminal
        transitions (the caller commits).
        """
        doc = await anyio.to_thread.run_sync(read_status, experiment.id, DATA_DIR)
        dir_exists = await anyio.Path(DATA_DIR / experiment.id).exists()

        if experiment.archived_at is not None:
            # Restore lifecycle; a non-restore doc is stale from the archive attempt.
            if doc is not None and doc.direction == ArchiveDirection.RESTORE.value:
                if doc.state == ArchiveState.COMPLETED.value:
                    experiment.archived_at = None
                    experiment.archived_step = None
                    experiment.archived_status = None
                    experiment.archived_size_bytes = None
                    return None
                # A live Job outranks a stale FAILED sentinel; an in-flight doc with
                # no live Job failed (evicted, backoffLimit 0), as in the archive direction.
                live = await self._is_job_live(ArchiveDirection.RESTORE.value, experiment.id)
                return "restoring" if live else "restore_failed"
            live = await self._is_job_live(ArchiveDirection.RESTORE.value, experiment.id)
            return "restoring" if live else "archived"

        if not dir_exists:
            if not await self._is_job_live(ArchiveDirection.ARCHIVE.value, experiment.id):
                experiment.archived_at = datetime.now(UTC)
                return "archived"
            return "archiving"

        if (
            doc is not None
            and doc.direction == ArchiveDirection.ARCHIVE.value
            and doc.state == ArchiveState.FAILED.value
        ):
            return "archive_failed"

        live = await self._is_job_live(ArchiveDirection.ARCHIVE.value, experiment.id)
        return "archiving" if live else "archive_failed"

    async def archive(self, experiment: Experiment) -> str:
        """
        Submit a durable archive Job after gating and snapshotting card state.

        Returns:
            The archive attempt ID.

        Raises:
            ApiError: S3 unconfigured (400 `urn:mddash:s3-not-configured`); gate
                failures (409 `urn:mddash:archive-conflict`); submission failure
                (409 `urn:mddash:archive-submission-failed`).
        """
        if not S3_BUCKET:
            raise _s3_not_configured("archiving")
        state = await self.refresh_state(experiment)
        if state not in {None, "archive_failed"}:
            raise ApiError(
                HTTPStatus.CONFLICT,
                f"Experiment cannot be archived now (state: {state}).",
                "urn:mddash:archive-conflict",
            )
        if await read_upload_state(self._k8s, experiment.id, DATA_DIR) in UploadState.active():
            raise ApiError(
                HTTPStatus.CONFLICT,
                "Cannot archive during an active MDRepo upload. Wait for completion or retry after failure.",
                "urn:mddash:archive-conflict",
            )
        await self._jobs.refresh(experiment)
        if self._jobs.live_jobs(experiment):
            raise ApiError(
                HTTPStatus.CONFLICT,
                "Cannot archive while tuner, simulation, or analysis jobs are running.",
                "urn:mddash:archive-conflict",
            )

        # Stopping the notebook matches deletion: archiving freezes the files under it.
        await self._notebooks.stop_if_running(experiment.notebook)

        step, status, size = await anyio.to_thread.run_sync(
            lambda: (experiment.step, experiment.status, experiment.size_bytes)
        )
        experiment.archived_step = step
        experiment.archived_status = status
        experiment.archived_size_bytes = size
        await self._session.commit()

        try:
            attempt_id = await submission.submit_job(self._k8s, ArchiveDirection.ARCHIVE.value, experiment.id, DATA_DIR)
        except submission.SubmissionError as e:
            raise ApiError(
                HTTPStatus.CONFLICT,
                "The archive job could not be started right now.",
                "urn:mddash:archive-submission-failed",
                "Try again in a moment; if the problem persists, contact support.",
            ) from e
        logger.info("Archive Job submitted for experiment %s (attempt %s)", experiment.id, attempt_id)
        return attempt_id

    async def restore(self, experiment: Experiment) -> str:
        """
        Submit a durable restore Job for an archived experiment.

        Returns:
            The restore attempt ID.

        Raises:
            ApiError: S3 unconfigured (400 `urn:mddash:s3-not-configured`); gate
                failures (409 `urn:mddash:archive-conflict`); submission failure
                (409 `urn:mddash:archive-submission-failed`).
        """
        if not S3_BUCKET:
            raise _s3_not_configured("restoring")
        state = await self.refresh_state(experiment)
        if state not in {"archived", "restore_failed"}:
            raise ApiError(
                HTTPStatus.CONFLICT,
                f"Experiment cannot be restored now (state: {state}).",
                "urn:mddash:archive-conflict",
            )
        if await anyio.Path(DATA_DIR / experiment.id).exists():
            # Worker-gate mirror: non-completed restore doc = our resumable leftover; else clobber protection.
            doc = await anyio.to_thread.run_sync(read_status, experiment.id, DATA_DIR)
            retryable = (
                doc is not None
                and doc.direction == ArchiveDirection.RESTORE.value
                and doc.state != ArchiveState.COMPLETED.value
            )
            if not retryable:
                raise ApiError(
                    HTTPStatus.CONFLICT,
                    "Local experiment directory already exists; refusing to overwrite it. "
                    "Remove the leftover directory manually and retry.",
                    "urn:mddash:archive-conflict",
                )

        try:
            attempt_id = await submission.submit_job(self._k8s, ArchiveDirection.RESTORE.value, experiment.id, DATA_DIR)
        except submission.SubmissionError as e:
            raise ApiError(
                HTTPStatus.CONFLICT,
                "The restore job could not be started right now.",
                "urn:mddash:archive-submission-failed",
                "Try again in a moment; if the problem persists, contact support.",
            ) from e
        logger.info("Restore Job submitted for experiment %s (attempt %s)", experiment.id, attempt_id)
        await self._session.commit()
        return attempt_id

    async def status(self, experiment: Experiment) -> dict:
        """Archive/restore status for the status endpoint: reconciliation result + status doc fields."""
        archive_state = await self.refresh_state(experiment)
        await self._session.commit()
        doc = await anyio.to_thread.run_sync(read_status, experiment.id, DATA_DIR)
        return {
            "experiment_id": experiment.id,
            "archive_state": archive_state,
            "attempt_id": doc.attempt_id if doc else None,
            "direction": doc.direction if doc else None,
            "reason": doc.reason if doc else None,
        }

    async def delete_jobs(self, experiment_id: str) -> None:
        """Delete in-flight archive/restore Jobs (deletion wins over them)."""
        await submission.delete_jobs(self._k8s, experiment_id)

    async def purge(self, experiment_id: str) -> None:
        """Best-effort deletion of the experiment's S3 archive prefix."""
        await submission.submit_purge_job(self._k8s, experiment_id)


ArchiveServiceDep = Annotated[ArchiveService, Depends()]
