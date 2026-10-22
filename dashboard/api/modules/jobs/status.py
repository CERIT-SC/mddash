"""Remote job status read once per request, with the last known status persisted as the offline fallback."""

import logging
from collections.abc import Awaitable, Callable

import sqlalchemy as sa
from cachetools import TTLCache
from core.enums import JobStatus
from sqlalchemy.orm import Mapped, mapped_column

logger = logging.getLogger(__name__)


class RecordedStatus:
    """Mixin for job rows whose status lives upstream (MDRun, Kubernetes); services record what they read."""

    # Last successfully-fetched non-UNKNOWN status (fallback when the upstream is unavailable)
    _last_known_status: Mapped[JobStatus | None] = mapped_column("last_known_status", sa.Enum(JobStatus), nullable=True)

    # Transient: status fetched by the job's service for this request
    _fetched_status: JobStatus | None = None

    def record_status(self, fetched: JobStatus) -> bool:
        """Store the status read for this request; True when it persisted as the new offline fallback."""
        changed = fetched not in {self._last_known_status, JobStatus.UNKNOWN}
        if changed:
            self._last_known_status = fetched
        self._fetched_status = fetched
        return changed

    def record_status_unavailable(self) -> None:
        """Serve the last known status (the upstream could not be read)."""
        self._fetched_status = self._last_known_status or JobStatus.UNKNOWN

    @property
    def settled_status(self) -> JobStatus | None:
        """The last known status once terminal: it never changes again, so it needs no upstream read."""
        status = self._last_known_status
        return status if status is not None and status.is_terminal else None

    @property
    def status(self) -> JobStatus:
        """
        Current upstream status, as recorded by the job's service in this request.

        Raises:
            RuntimeError: If an unsettled job was not refreshed in this request.
        """
        if settled := self.settled_status:
            return settled
        if self._fetched_status is None:
            raise RuntimeError(f"Status of {type(self).__name__} {getattr(self, 'id', '?')} read before refresh")
        return self._fetched_status


async def refresh_recorded(
    job: RecordedStatus, job_id: str, cache: TTLCache, fetch: Callable[[], Awaitable[JobStatus]]
) -> bool:
    """
    Record the job's upstream status: settled jobs skip the read, fresh reads coalesce in `cache`.

    Returns True when a new status persisted; an unreachable upstream serves the last known one.
    """
    if settled := job.settled_status:
        job.record_status(settled)
        return False
    try:
        fetched = cache.get(job_id)
        if fetched is None:
            fetched = await fetch()
            cache[job_id] = fetched
        return job.record_status(fetched)
    except Exception:
        logger.exception("Error fetching status of %s %s", type(job).__name__, job_id)
        job.record_status_unavailable()
        return False
