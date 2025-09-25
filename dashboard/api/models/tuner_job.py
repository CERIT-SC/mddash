import json
import logging
from pathlib import Path
from datetime import datetime
from cachetools import TTLCache, cached
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy import Text

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
    # whether the job was stopped (preserves data but job is deleted from tuner)
    is_stopped: Mapped[bool] = mapped_column(db.Boolean, default=False, nullable=False)
    # preserved status data when job is stopped
    _preserved_summary: Mapped[str] = mapped_column('preserved_summary', Text, nullable=True)
    _preserved_trials: Mapped[str] = mapped_column('preserved_trials', Text, nullable=True) 
    _preserved_cluster_resources: Mapped[str] = mapped_column('preserved_cluster_resources', db.String(255), nullable=True)

    # back-reference to the parent experiment
    experiment: Mapped['Experiment'] = relationship('Experiment', back_populates='tuner_jobs')

    @property
    def summary(self) -> dict:
        '''Summary of the tuner trial statuses.'''
        if self.is_stopped and self._preserved_summary:
            return json.loads(self._preserved_summary)
        return self._status().get('summary', {})

    @property
    def trials(self) -> list[dict]:
        '''Trial jobs with their statuses.'''
        if self.is_stopped and self._preserved_trials:
            return json.loads(self._preserved_trials)
        return self._status().get('trials', [])

    @property
    def cluster_resources(self) -> str:
        '''Cluster resources used by the tuner jobs.'''
        if self.is_stopped and self._preserved_cluster_resources:
            return self._preserved_cluster_resources
        return self._status().get('cluster_resources', 'N/A')

    @cached(cache=status_cache)
    def _status(self) -> dict:
        if self.is_stopped:
            return {}
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

    def stop(self) -> None:
        '''
        Stop the tuner job and preserve its current status.
        The job gets deleted from the tuner but data is preserved in the database.
        
        :raise HTTPError: If the tuner api request fails.
        '''
        if self.is_stopped:
            return

        current_status = self._status()

        # Convert RUNNING trials to TERMINATED
        trials = current_status.get('trials', [])
        for trial in trials:
            if trial.get('status') == 'RUNNING':
                trial['status'] = 'TERMINATED'

        # Update summary counts
        summary = current_status.get('summary', {})
        terminated_count = summary.get('TERMINATED', 0) + summary.get('RUNNING', 0)
        summary['TERMINATED'] = terminated_count
        summary['RUNNING'] = 0

        self._preserved_summary = json.dumps(summary)
        self._preserved_trials = json.dumps(trials)
        self._preserved_cluster_resources = current_status.get('cluster_resources', 'N/A')
        self.is_stopped = True

        tuner.delete_job(self.tuner_run_id)

        status_cache.clear()
        logger.info(f"Stopped tuner job {self.tuner_run_id}")

    def delete(self) -> None:
        '''
        Delete the tuner job completely.

        :raise HTTPError: If the tuner api request fails.
        '''
        if not self.is_stopped:
            tuner.delete_job(self.tuner_run_id)
