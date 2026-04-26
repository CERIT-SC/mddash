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
        """Get the current job status from Kubernetes and update the database."""
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

    def handle_status_change(self, old: JobStatus, new: JobStatus) -> None:
        """Handle job status transitions and cleanup finalized jobs."""
        logger.info(f"MDRun job {self.job_name} status changed from {old} to {new}")

        if new in {JobStatus.TERMINATED, JobStatus.ERROR}:
            self.delete()
