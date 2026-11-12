import logging
from dataclasses import asdict
from datetime import UTC, datetime
from uuid import uuid4

import k8s_client
from config import NAMESPACE
from enums import JobStatus, UsageOutcome
from extensions import db
from kubernetes.client.rest import ApiException
from sqlalchemy import update
from sqlalchemy.dialects.sqlite import insert
from sqlalchemy.orm import Mapped, mapped_column, relationship
from urllib3.exceptions import HTTPError

logger = logging.getLogger(__name__)

_TERMINAL = frozenset({JobStatus.FINISHED, JobStatus.ERROR, JobStatus.STOPPED})
_K8S_ERRORS = (ApiException, HTTPError)


class MdrunUsage(db.Model):  # type: ignore
    """
    Per-user accounting record of one job's resource allocation.

    Rows are never deleted: they outlive their job rows, which DELETE removes.
    """

    __tablename__ = "mdrun_usage"

    job_id: Mapped[str] = mapped_column(db.String(36), primary_key=True)
    engine: Mapped[str] = mapped_column(db.String(16), nullable=False)
    owner: Mapped[str | None] = mapped_column(db.String(255))
    owner_namespace: Mapped[str | None] = mapped_column(db.String(63))
    experiment_id: Mapped[str] = mapped_column(db.String(255), nullable=False)
    cpu_cores: Mapped[int] = mapped_column(nullable=False)
    memory_gib: Mapped[int] = mapped_column(nullable=False)
    gpus: Mapped[int] = mapped_column(nullable=False)
    created_at: Mapped[datetime] = mapped_column(db.DateTime, default=lambda: datetime.now(UTC))
    started_at: Mapped[datetime | None] = mapped_column(db.DateTime)
    finished_at: Mapped[datetime | None] = mapped_column(db.DateTime)
    outcome: Mapped[UsageOutcome | None] = mapped_column(db.Enum(UsageOutcome))
    # Load with selectinload when reading many records.
    measurement: Mapped["MdrunUsageMeasurement | None"] = relationship()


class MdrunUsageMeasurement(db.Model):  # type: ignore
    """
    A job's self-measurement, mirroring ``k8s_client.MeasuredUsage``; ``complete`` marks the container's exit line.

    ``create_all`` never adds columns to an existing table: a new column needs ``ALTER TABLE`` where the table exists.
    """

    __tablename__ = "mdrun_usage_measured"

    job_id: Mapped[str] = mapped_column(db.String(36), db.ForeignKey("mdrun_usage.job_id"), primary_key=True)
    cpu_core_seconds: Mapped[float | None] = mapped_column()
    memory_peak_gib: Mapped[float | None] = mapped_column()
    gpu_utilization: Mapped[float | None] = mapped_column()
    gpu_memory_peak_gib: Mapped[float | None] = mapped_column()
    complete: Mapped[bool] = mapped_column(nullable=False)
    container_started_at: Mapped[datetime | None] = mapped_column(db.DateTime)
    measured_at: Mapped[datetime | None] = mapped_column(db.DateTime)
    cpu_throttled_seconds: Mapped[float | None] = mapped_column()
    cpu_stall_seconds: Mapped[float | None] = mapped_column()
    memory_stall_seconds: Mapped[float | None] = mapped_column()
    io_stall_seconds: Mapped[float | None] = mapped_column()
    oom_kills: Mapped[int | None] = mapped_column()
    io_read_bytes: Mapped[int | None] = mapped_column()
    io_write_bytes: Mapped[int | None] = mapped_column()
    gpu_power_watts: Mapped[float | None] = mapped_column()
    ns_per_day: Mapped[float | None] = mapped_column()


class MdrunJob(db.Model):  # type: ignore
    """SQLAlchemy model representing a simulation job."""

    __tablename__ = "mdrun_jobs"

    id: Mapped[str] = mapped_column(db.String(36), primary_key=True, default=lambda: str(uuid4()))
    created_at: Mapped[datetime] = mapped_column(db.DateTime, default=lambda: datetime.now(UTC))
    job_name: Mapped[str] = mapped_column(db.String(255), nullable=False)
    experiment_id: Mapped[str] = mapped_column(db.String(255), nullable=False)
    last_status: Mapped[JobStatus] = mapped_column(db.Enum(JobStatus), default=JobStatus.PENDING, nullable=False)

    @classmethod
    def create(
        cls,
        job_id: str,
        job_name: str,
        experiment_id: str,
        *,
        engine: str,
        resources: k8s_client.JobResources,
        owner: str | None,
        owner_namespace: str | None,
    ) -> "MdrunJob":
        """
        Persist a new job record together with its usage record.

        Args:
            job_id: Unique identifier for the job (matches the uuid in job_name).
            job_name: Kubernetes job name (format: mdrun-{uuid}).
            experiment_id: Experiment this job belongs to.
            engine: API path segment (`gmx`, `amber`).
            resources: What the simulation container reserves.
            owner: Submitting user; None records the job as unattributed.
            owner_namespace: The user's namespace; None records the job as unattributed.

        Returns:
            The created MdrunJob instance.
        """
        job = cls(id=job_id, job_name=job_name, experiment_id=experiment_id)  # type: ignore[call-arg]
        usage = MdrunUsage(
            job_id=job_id,
            engine=engine,
            owner=owner,
            owner_namespace=owner_namespace,
            experiment_id=experiment_id,
            cpu_cores=resources.cpu,
            memory_gib=resources.memory_gib,
            gpus=resources.gpus,
        )
        db.session.add_all([job, usage])
        db.session.commit()
        logger.info(f"Created job {job_name} for experiment {experiment_id}")
        return job

    @property
    def usage(self) -> MdrunUsage | None:
        """The job's usage record; None for jobs created before the ledger existed."""
        return db.session.get(MdrunUsage, self.id)

    @property
    def status(self) -> JobStatus:
        """
        The current job status from Kubernetes; the database row is updated as a side effect.

        A failed read raises and leaves the row, the usage window, and the Job as they are.
        """
        # STOPPED is sticky: the row outlives its K8s job, which K8s still reports
        # as RUNNING through the graceful-deletion window. Trusting it would resurrect the row.
        if self.last_status == JobStatus.STOPPED:
            return JobStatus.STOPPED

        job_status = k8s_client.get_job_status(ns=NAMESPACE, name=self.job_name)

        if job_status == JobStatus.UNKNOWN:
            # Vanished before a terminal status was seen; stop its usage from accruing.
            if self.last_status not in _TERMINAL:
                self.record_usage(UsageOutcome.UNKNOWN)
                db.session.commit()
            return self.last_status

        if job_status != self.last_status:
            self.handle_status_change(self.last_status, job_status)
            self.last_status = job_status
            db.session.commit()

        return job_status

    def delete(self) -> None:
        """Delete the Kubernetes job resource."""
        k8s_client.delete_job(ns=NAMESPACE, name=self.job_name)

    def stop(self) -> None:
        """
        Stop the job with extended grace (checkpoint + s3-sync upload), keeping the DB row.

        Outcome is re-read after deletion: a run that finishes before teardown stays FINISHED.
        """
        if self.status in _TERMINAL:
            return

        self.record_usage(UsageOutcome.STOPPED)
        k8s_client.delete_job(
            ns=NAMESPACE, name=self.job_name, grace_period_seconds=k8s_client.STOP_GRACE_PERIOD_SECONDS
        )
        try:
            outcome = k8s_client.get_job_status(ns=NAMESPACE, name=self.job_name)
        except _K8S_ERRORS:
            # The delete went through: the stop holds whatever the outcome was.
            logger.warning("Outcome of stopped job %s is unreadable", self.job_name, exc_info=True)
            outcome = JobStatus.STOPPED
        self.last_status = JobStatus.FINISHED if outcome == JobStatus.FINISHED else JobStatus.STOPPED
        db.session.commit()

    def record_usage(self, outcome: UsageOutcome | None = None) -> None:
        """
        Stamp the allocation window from the job's pod; an ``outcome`` also closes it and stores the measurement.

        Times the pod no longer reports fall back to now. Writes only fill unset fields and hit the database at
        once, so call this before deleting the Job: a concurrent status read that then finds the Job gone waits
        on the write lock and leaves the closed window as it is.
        """
        usage = self.usage
        if usage is None or usage.finished_at is not None:
            return

        # Kubernetes first: the writes below hold SQLite's write lock until the caller commits.
        pod = k8s_client.get_job_pod(ns=NAMESPACE, name=self.job_name)
        start, end = k8s_client.get_pod_times(pod)
        measured = None if outcome is None else k8s_client.get_measured_usage(ns=NAMESPACE, name=self.job_name, pod=pod)
        now = datetime.now(UTC)
        window = update(MdrunUsage).where(MdrunUsage.job_id == self.id).execution_options(synchronize_session=False)
        db.session.execute(window.where(MdrunUsage.started_at.is_(None)).values(started_at=start or now))
        if outcome is not None:
            db.session.execute(
                window.where(MdrunUsage.finished_at.is_(None)).values(finished_at=end or now, outcome=outcome)
            )
        if measured is not None:
            db.session.execute(
                insert(MdrunUsageMeasurement).values(job_id=self.id, **asdict(measured)).on_conflict_do_nothing()
            )

    def handle_status_change(self, old: JobStatus, new: JobStatus) -> None:
        """Record usage on job status transitions and clean up finalized jobs."""
        logger.info(f"MDRun job {self.job_name} status changed from {old} to {new}")

        if new == JobStatus.RUNNING:
            self.record_usage()
        elif new in {JobStatus.FINISHED, JobStatus.ERROR}:
            # Before the delete: it removes the pod and its timestamps, and concurrent reads must find the window closed.
            self.record_usage(UsageOutcome(new.value))
            try:
                self.delete()
            except _K8S_ERRORS:
                # The outcome is real either way; ttlSecondsAfterFinished removes the Job.
                logger.warning("Cleanup of %s job %s failed", new, self.job_name, exc_info=True)
