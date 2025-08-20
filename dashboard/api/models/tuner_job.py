import logging
from pathlib import Path
from datetime import datetime
from cachetools import TTLCache, cached
from sqlalchemy.orm import Mapped, mapped_column, relationship

from clients import tuner
from extensions import db
from .experiment import Experiment


logger = logging.getLogger(__name__)
status_cache: TTLCache = TTLCache(maxsize=100, ttl=0.2)  # 200ms


class TunerJob(db.Model):  # type: ignore
    __tablename__ = 'tuner_jobs'

    # ID of the tune job
    tuner_run_id: Mapped[str] = mapped_column(db.String(36), primary_key=True, nullable=False)
    # ID of the experiment this job belongs to
    experiment_id: Mapped[str] = mapped_column(db.String(5), db.ForeignKey('experiments.id'))
    # name of the TPR file being tuned
    tpr_name: Mapped[str] = mapped_column(db.String(255), nullable=False)
    # creation time
    created_at: Mapped[datetime] = mapped_column(db.DateTime, default=datetime.now)

    # back-reference to the parent experiment
    experiment: Mapped['Experiment'] = relationship('Experiment', back_populates='tuner_jobs')

    @property
    def summary(self) -> dict:
        '''Summary of the tuner trial statuses.'''
        return self._status().get('summary', {})

    @property
    def trials(self) -> list[dict]:
        '''Trial jobs with their statuses.'''
        return self._status().get('trials', [])

    @property
    def cluster_resources(self) -> str:
        '''Cluster resources used by the tuner jobs.'''
        return self._status().get('cluster_resources', 'N/A')

    @cached(cache=status_cache)
    def _status(self) -> dict:
        try:
            return tuner.poll_status(self.tuner_run_id)
        except Exception:
            logger.error(f"Failed to fetch status for tuner job {self.tuner_run_id}", exc_info=True)
            return {}

    @classmethod
    def start(cls, experiment: Experiment, tpr_path: Path) -> 'TunerJob':
        '''
        Start a tuner job for the given experiment and TPR file.

        :param experiment: The parent experiment
        :param tpr_path: Path to the TPR file
        :return: The created TunerJob instance
        :raise FileNotFoundError: If the TPR file does not exist.
        :raise HTTPError: If the tuner api request fails.
        '''
        response = tuner.run_submit(tpr_path)
        job = cls(
            tuner_run_id=response['tuner_run_id'],
            tpr_name=tpr_path.name,
            experiment=experiment
        )
    
        db.session.add(job)
        db.session.commit()
        logger.info(f"Started tuner job {job.tuner_run_id} for experiment {experiment.id} with TPR {tpr_path.name}")
        
        return job

    def delete(self) -> None:
        '''
        Delete the tuner job.

        :raise HTTPError: If the tuner api request fails.
        '''
        tuner.delete_job(self.tuner_run_id)
