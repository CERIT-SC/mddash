import logging
import io
import requests
import zipfile
from uuid import uuid4
from shutil import rmtree
from datetime import datetime
from typing import TYPE_CHECKING
from cachetools import TTLCache, cached
from werkzeug.datastructures import FileStorage
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy.orm import Mapped, mapped_column, relationship

from enums import PodStatus, JobStatus
from utils import get_files_with_extension, get_unique_id
from config import DATA_DIR

if TYPE_CHECKING:
    from .notebook import Notebook
    from .tuner_job import TunerJob
    from .gromacs_job import GromacsJob


db = SQLAlchemy()
logger = logging.getLogger(__name__)
step_status_cache: TTLCache = TTLCache(maxsize=100, ttl=0.1)  # 100ms


class Experiment(db.Model):  # type: ignore
    __tablename__ = 'experiments'

    # unique ID of the experiment, also used as the directory name
    id: Mapped[str] = mapped_column(db.String(5), primary_key=True)
    # creation time
    created_at: Mapped[datetime] = mapped_column(db.DateTime, default=datetime.now)
    # last modification time
    updated_at: Mapped[datetime] = mapped_column(db.DateTime, default=datetime.now, onupdate=datetime.now)
    # name of the experiment
    name: Mapped[str] = mapped_column(db.String(255), nullable=False)
    # message for user to understand the source of the experiment
    source_message: Mapped[str | None] = mapped_column(db.Text, nullable=True)
    # token for accessing jupyter notebook
    token: Mapped[str] = mapped_column(db.String(36), nullable=False)
    # ID of the experiment in MDRepo
    mdrepo_id: Mapped[str | None] = mapped_column(db.String(255), nullable=True)

    # Setup notebook status
    notebook: Mapped['Notebook'] = relationship('Notebook', back_populates='experiment', cascade='all, delete-orphan', uselist=False) 
    # Tuner jobs of the experiment
    tuner_jobs: Mapped[list['TunerJob']] = relationship('TunerJob', back_populates='experiment', cascade='all, delete-orphan')
    # GROMACS jobs of the experiment
    gromacs_jobs: Mapped[list['GromacsJob']] = relationship('GromacsJob', back_populates='experiment', cascade='all, delete-orphan')

    @property
    def step(self) -> int:
        '''Step of the experiment based on its current state.'''
        return self._step_status()[0]

    @property
    def status(self) -> str:
        '''Status of the experiment based on its current state.'''
        return self._step_status()[1]

    @classmethod
    def prepare_env(cls) -> str:
        """Prepare environment directory for new experiment."""
        experiment_id: str = get_unique_id(DATA_DIR)
        (DATA_DIR / experiment_id).mkdir(parents=True, exist_ok=True)
        return experiment_id

    @classmethod
    def from_pdb(cls, name: str, pdb_id: str) -> 'Experiment':
        """
        Create experiment from PDB ID with database persistence.
        
        :param name: Name of the experiment.
        :param pdb_id: PDB ID to download (e.g., 1A2B).
        :return: The created Experiment instance.
        :raises ValueError: If the PDB ID is invalid or not found.
        :raises Exception: If the PDB file cannot be downloaded or processed.
        """
        experiment_id: str = cls.prepare_env()
        pdb_id = pdb_id.strip().upper()

        try:
            # Download PDB file
            url: str = f"https://files.rcsb.org/download/{pdb_id}.pdb"
            response = requests.get(url)

            if response.status_code == 404:
                raise ValueError(f"PDB ID '{pdb_id}' not found.")
            elif response.status_code != 200:
                raise ValueError(f"Failed to download PDB file: {response.status_code}")

            with open(DATA_DIR / experiment_id / 'input.pdb', 'wb') as f:
                f.write(response.content)

            # Create experiment instance
            message: str = f"Created by downloading '{pdb_id}' from RCSB PDB."
            experiment = cls(
                id=experiment_id,
                name=name,
                source_message=message,
                token=str(uuid4())
            )

            # Save to database
            db.session.add(experiment)
            db.session.commit()

            logger.info(f"Created experiment {experiment_id} from PDB {pdb_id}")
            return experiment

        except Exception:
            # Cleanup on failure
            rmtree(DATA_DIR / experiment_id, ignore_errors=True)
            db.session.rollback()
            raise

    @classmethod
    def from_repo(cls, name: str, repo_link: str) -> 'Experiment':
        """
        Create experiment from Zenodo repository with database persistence.
        
        :param name: Name of the experiment.
        :param repo_link: Zenodo repository link (e.g., https://zenodo.org/record/1234567).
        :return: The created Experiment instance.
        :raises ValueError: If the repository link is invalid or not found.
        :raises Exception: If the repository cannot be downloaded or processed.
        """
        experiment_id: str = cls.prepare_env()

        try:
            # Validate and parse repository link
            repo_link_parts: list[str] = repo_link.strip().split('/')
            if len(repo_link_parts) < 4 or repo_link_parts[2] != 'zenodo.org':
                raise ValueError('Invalid repository link (expected zenodo.org)')

            record_id: str = repo_link_parts[-1]
            url: str = f"https://zenodo.org/api/records/{record_id}/files-archive"
            response = requests.get(url)

            if response.status_code == 404:
                raise ValueError(f"Repository '{repo_link}' not found.")
            elif response.status_code != 200:
                raise ValueError(f"Failed to download repository: {response.status_code}")

            # Extract zip file
            with zipfile.ZipFile(io.BytesIO(response.content)) as zf:
                zf.extractall(DATA_DIR / experiment_id)

            # Create experiment instance
            message: str = f"Created by downloading repository from '{repo_link}'."
            experiment = cls(
                id=experiment_id,
                name=name,
                source_message=message,
                token=str(uuid4())
            )

            # Save to database
            db.session.add(experiment)
            db.session.commit()
            
            logger.info(f"Created experiment {experiment_id} from repository {repo_link}")
            return experiment

        except Exception as e:
            # Cleanup on failure
            rmtree(DATA_DIR / experiment_id, ignore_errors=True)
            db.session.rollback()
            raise

    @classmethod
    def from_tpr(cls, name: str, tpr: FileStorage) -> 'Experiment':
        """
        Create experiment from TPR file upload with database persistence.
        
        :param name: Name of the experiment.
        :param tpr: Uploaded TPR file.
        :return: The created Experiment instance.
        :raises ValueError: If the TPR file is invalid or cannot be processed.
        """
        if not tpr.filename or not tpr.filename.endswith('.tpr'):
            raise ValueError('Invalid file format (expected .tpr)')

        experiment_id: str = cls.prepare_env()

        try:
            # Save TPR file
            tpr.save(DATA_DIR / experiment_id / 'input.tpr')

            # Create experiment instance
            message: str = f"Created by uploading TPR file '{tpr.filename}'."
            experiment = cls(
                id=experiment_id,
                name=name,
                source_message=message,
                token=str(uuid4())
            )

            # Save to database
            db.session.add(experiment)
            db.session.commit()
            
            logger.info(f"Created experiment {experiment_id} from TPR file {tpr.filename}")
            return experiment

        except Exception:
            # Cleanup on failure
            rmtree(DATA_DIR / experiment_id, ignore_errors=True)
            db.session.rollback()
            raise

    @cached(cache=step_status_cache)
    def _step_status(self) -> tuple[int, str]:
        """
        Determine (step, status) based on current state.
        """
        # Step 5: Published (experiment has mdrepo_id)
        if self.mdrepo_id:
            return 5, 'published'

        # Step 4: Analyzing (experiment has terminated GROMACS job)
        if any(j.status == JobStatus.TERMINATED for j in self.gromacs_jobs):
            return 4, 'analyzing'

        # NOTE: Step 3 is skipped because no action is required to progress from Analyze to Publish

        # Step 2: Running simulation (experiment has running GROMACS job)
        if any(j.status == JobStatus.RUNNING for j in self.gromacs_jobs):
            return 2, 'simulating'

        # Step 2: Tuning (experiment has terminated tuner job)
        if any(j.status.get('summary', {}).get('TERMINATED', 0) > 0 for j in self.tuner_jobs):
            return 2, 'tuning'

        # Step 1: Tuning (experiment has running tuner job)
        if any(j.status.get('summary', {}).get('RUNNING', 0) > 0 for j in self.tuner_jobs):
            return 1, 'tuning'

        # Step 1: Setup complete (directory contains a TPR file)
        if get_files_with_extension(DATA_DIR / self.id, 'tpr'):
            return 1, 'setup complete'

        return 0, 'setup'

    def delete_resources(self) -> None:
        """
        Delete the experiment and all its related resources.
        """

        # Delete notebook pod if it exists
        if self.notebook.status == PodStatus.RUNNING:
            self.notebook.stop()            

        # Delete tuner jobs
        for tuner_job in self.tuner_jobs:
            try:
                tuner_job.delete()
            except Exception:
                logger.error(f'Failed to delete tuner job {tuner_job.tuner_run_id}:', exc_info=True)

        # Delete GROMACS jobs
        for gmx_job in self.gromacs_jobs:
            try:
                gmx_job.delete()
            except Exception:
                logger.error(f'Failed to delete GROMACS job {gmx_job.job_name}:', exc_info=True)

        # Delete all files in the experiment directory
        rmtree(DATA_DIR / self.id, ignore_errors=True)
