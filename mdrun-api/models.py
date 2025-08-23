import logging
from uuid import uuid4
from datetime import datetime
from sqlalchemy.orm import Mapped, mapped_column

from config import NAMESPACE, DATA_DIR
from enums import DeviceType, JobStatus
from extensions import db
import k8s_client

logger = logging.getLogger(__name__)


class MdrunJob(db.Model):  # type: ignore
    __tablename__ = 'mdrun_jobs'

    id: Mapped[str] = mapped_column(db.String(36), primary_key=True, default=lambda: str(uuid4()))
    created_at: Mapped[datetime] = mapped_column(db.DateTime, default=datetime.now)
    job_name: Mapped[str] = mapped_column(db.String(255), nullable=False)
    experiment_id: Mapped[str] = mapped_column(db.String(255), nullable=False)

    @property
    def status(self) -> JobStatus:
        return k8s_client.get_job_status(ns=NAMESPACE, name=self.job_name)

    @classmethod
    def create_and_start(
        cls,
        experiment_id: str,
        tpr_name: str,
        pvc_name: str,
        pme: DeviceType,
        nb: DeviceType,
        np: int,
        ntomp: int,
        extra_args: str = ''
    ) -> 'MdrunJob':
        job_id = str(uuid4())
        job_name = f'mdrun-{job_id}'

        # Check if TPR file exists in experiment directory
        tpr_path = DATA_DIR / experiment_id / tpr_name
        if not tpr_path.exists():
            raise FileNotFoundError(f"TPR file {tpr_name} not found in experiment {experiment_id}")

        # Ensure PVC exists in admin namespace
        k8s_client.create_pvc(ns=NAMESPACE, pvc_name=pvc_name)

        # Create Kubernetes job - this should fail if it can't be created
        deffnm = tpr_name.removesuffix('.tpr')
        k8s_client.create_gromacs_job(
            ns=NAMESPACE,
            pvc=pvc_name,
            name=job_name,
            experiment_id=experiment_id,
            deffnm=deffnm,
            nb=nb.value,
            pme=pme.value,
            np=np,
            ntomp=ntomp,
            extra_args=extra_args
        )

        # Only create DB record if K8s job creation succeeded
        job = cls(
            id=job_id,
            job_name=job_name,
            experiment_id=experiment_id
        )

        db.session.add(job)
        db.session.commit()
        logger.info(f"Started MDRun job {job_name} with ID {job_id} in experiment {experiment_id}")
        
        return job

    def delete(self) -> None:
        k8s_client.delete_job(ns=NAMESPACE, name=self.job_name)
        logger.info(f"Deleted MDRun job {self.job_name} with ID {self.id}")
