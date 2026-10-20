"""Remote job status read once per request, with the last known status persisted as the offline fallback."""

import sqlalchemy as sa
from core.enums import JobStatus
from sqlalchemy.orm import Mapped, mapped_column


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
