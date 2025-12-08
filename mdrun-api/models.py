import logging
from datetime import datetime
from uuid import uuid4

import k8s_client
from config import NAMESPACE
from enums import DeviceType, JobStatus
from extensions import db
from sqlalchemy.orm import Mapped, mapped_column

logger = logging.getLogger(__name__)


class MdrunJob(db.Model):  # type: ignore
    """SQLAlchemy model representing a GROMACS MD simulation job."""

    __tablename__ = "mdrun_jobs"

    id: Mapped[str] = mapped_column(db.String(36), primary_key=True, default=lambda: str(uuid4()))
    created_at: Mapped[datetime] = mapped_column(db.DateTime, default=lambda: datetime.now())
    job_name: Mapped[str] = mapped_column(db.String(255), nullable=False)
    experiment_id: Mapped[str] = mapped_column(db.String(255), nullable=False)
    last_status: Mapped[JobStatus] = mapped_column(db.Enum(JobStatus), default=JobStatus.PENDING, nullable=False)

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

    @classmethod
    def create_and_start(
        cls,
        experiment_id: str,
        tpr_name: str,
        bucket_name: str,
        pme: DeviceType,
        nb: DeviceType,
        np: int,
        ntomp: int,
        extra_args: str = "",
    ) -> "MdrunJob":
        """
        Create a new job record and start the GROMACS simulation in Kubernetes.

        Args:
            experiment_id: Unique experiment identifier.
            tpr_name: Name of the TPR input file.
            bucket_name: S3 bucket for data storage.
            pme: Device type for PME calculations.
            nb: Device type for non-bonded interactions.
            np: Number of MPI processes.
            ntomp: Number of OpenMP threads per process.
            extra_args: Additional arguments for gmx mdrun.

        Returns:
            MdrunJob: The created MdrunJob instance.
        """
        job_id = str(uuid4())
        job_name = f"mdrun-{job_id}"

        # Create Kubernetes job - this should fail if it can't be created
        deffnm = tpr_name.removesuffix(".tpr")
        k8s_client.create_gromacs_job(
            ns=NAMESPACE,
            bucket_name=bucket_name,
            name=job_name,
            experiment_id=experiment_id,
            deffnm=deffnm,
            nb=nb.value,
            pme=pme.value,
            np=np,
            ntomp=ntomp,
            extra_args=extra_args,
        )

        # Only create DB record if K8s job creation succeeded
        job = cls(id=job_id, job_name=job_name, experiment_id=experiment_id)  # type: ignore[call-arg]

        db.session.add(job)
        db.session.commit()
        logger.info(f"Started MDRun job {job_name} with ID {job_id} in experiment {experiment_id}")

        return job

    def delete(self) -> None:
        """Delete the Kubernetes job resource."""
        k8s_client.delete_job(ns=NAMESPACE, name=self.job_name)

    def handle_status_change(self, old: JobStatus, new: JobStatus) -> None:
        """Handle job status transitions and cleanup finalized jobs."""
        logger.info(f"MDRun job {self.job_name} status changed from {old} to {new}")

        # Automatically delete finalized jobs (status is preserved in DB)
        if new == JobStatus.TERMINATED or new == JobStatus.ERROR:
            self.delete()
