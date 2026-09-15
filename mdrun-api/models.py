import logging
from datetime import UTC, datetime
from uuid import uuid4

import k8s_client
from config import NAMESPACE
from enums import JobStatus
from extensions import db
from sqlalchemy.orm import Mapped, mapped_column

logger = logging.getLogger(__name__)


class MdrunJob(db.Model):  # type: ignore
    """SQLAlchemy model representing a simulation job."""

    __tablename__ = "mdrun_jobs"

    id: Mapped[str] = mapped_column(db.String(36), primary_key=True, default=lambda: str(uuid4()))
    created_at: Mapped[datetime] = mapped_column(db.DateTime, default=lambda: datetime.now(UTC))
    job_name: Mapped[str] = mapped_column(db.String(255), nullable=False)
    experiment_id: Mapped[str] = mapped_column(db.String(255), nullable=False)
    last_status: Mapped[JobStatus] = mapped_column(db.Enum(JobStatus), default=JobStatus.PENDING, nullable=False)

    @classmethod
    def create(cls, job_id: str, job_name: str, experiment_id: str) -> "MdrunJob":
        """
        Persist a new job record.

        Args:
            job_id: Unique identifier for the job (matches the uuid in job_name).
            job_name: Kubernetes job name (format: mdrun-{uuid}).
            experiment_id: Experiment this job belongs to.

        Returns:
            The created MdrunJob instance.
        """
        job = cls(id=job_id, job_name=job_name, experiment_id=experiment_id)  # type: ignore[call-arg]
        db.session.add(job)
        db.session.commit()
        logger.info(f"Created job {job_name} for experiment {experiment_id}")
        return job

    @property
    def status(self) -> JobStatus:
        """The current job status from Kubernetes; the database row is updated as a side effect."""
        job_status = k8s_client.get_job_status(ns=NAMESPACE, name=self.job_name)

        if job_status == JobStatus.UNKNOWN:
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
        Stop the Kubernetes job gracefully, preserving its data.

        The pod gets an extended grace period so the simulation can write its final
        checkpoint and the s3-sync sidecar can upload it to S3 before teardown
        (see ``_sim_guard_block``/``_s3_sync_command`` in ``k8s_client``). The DB row is
        kept with status STOPPED — after the K8s job is gone, ``status`` falls back to
        ``last_status`` so the job keeps reporting ``stopped``. Terminal jobs (FINISHED,
        ERROR, STOPPED) are not flipped: a finished run is not a stopped run. The job
        may also finish between the check above and the deletion taking effect, so the
        outcome is re-read once before stamping.
        """
        if self.status in {JobStatus.FINISHED, JobStatus.ERROR, JobStatus.STOPPED}:
            return

        k8s_client.delete_job(
            ns=NAMESPACE, name=self.job_name, grace_period_seconds=k8s_client.STOP_GRACE_PERIOD_SECONDS
        )
        outcome = k8s_client.get_job_status(ns=NAMESPACE, name=self.job_name)
        self.last_status = JobStatus.FINISHED if outcome == JobStatus.FINISHED else JobStatus.STOPPED
        db.session.commit()

    def handle_status_change(self, old: JobStatus, new: JobStatus) -> None:
        """Handle job status transitions and cleanup finalized jobs."""
        logger.info(f"MDRun job {self.job_name} status changed from {old} to {new}")

        if new in {JobStatus.FINISHED, JobStatus.ERROR}:
            self.delete()
