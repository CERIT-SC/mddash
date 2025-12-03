import io
import logging
import requests
import zipfile
from shutil import rmtree
from flask import abort
from datetime import datetime
from typing import TYPE_CHECKING
from cachetools import TTLCache, cached
from werkzeug.datastructures import FileStorage
from sqlalchemy.orm import Mapped, mapped_column, relationship

from config import DATA_DIR
from enums import PodStatus, JobStatus
from utils import get_files_with_extensions, get_unique_id
from clients import mdrepo
from .notebook import Notebook
from extensions import db

if TYPE_CHECKING:
    from .tuner_job import TunerJob
    from .gromacs_job import GromacsJob


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
    source_message: Mapped[str | None] = mapped_column(db.Text, nullable=False)
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
    def _create_with_notebook(cls, experiment: 'Experiment') -> 'Experiment':
        """
        Helper method to create experiment with auto-generated notebook.
        
        :param experiment: The Experiment instance to create.
        :return: The created Experiment instance with an associated Notebook.
        :raises Exception: If there is an error during creation.
        """
        db.session.add(experiment)
        db.session.flush()

        notebook = Notebook(experiment_id=experiment.id)
        db.session.add(notebook)
        db.session.commit()
        
        logger.info(f"Created experiment {experiment.id}")
        return experiment

    @classmethod
    def from_pdb(cls, name: str, pdb_id: str) -> 'Experiment':
        """
        Create experiment from PDB ID with database persistence.
        
        :param name: Name of the experiment.
        :param pdb_id: PDB ID to download (e.g., 1A2B).
        :return: The created Experiment instance.
        :raises HTTPException: If the PDB ID is not found or download fails.
        """
        experiment_id: str = cls.prepare_env()
        pdb_id = pdb_id.strip().upper()

        try:
            # Download PDB file
            url: str = f"https://files.rcsb.org/download/{pdb_id}.pdb"
            response = requests.get(url)

            if response.status_code == 404:
                abort(404, description=f"PDB ID '{pdb_id}' not found.")
            elif response.status_code != 200:
                abort(500, description=f"Failed to download PDB file: {response.status_code}")

            with open(DATA_DIR / experiment_id / 'input.pdb', 'wb') as f:
                f.write(response.content)

            message: str = f"Created by downloading '{pdb_id}' from RCSB PDB."
            experiment = cls(
                id=experiment_id,
                name=name,
                source_message=message
            )

            return cls._create_with_notebook(experiment)

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
        :raises HTTPException: If the repository link is invalid or download fails.
        """
        experiment_id: str = cls.prepare_env()

        try:
            # Validate and parse repository link
            repo_link_parts: list[str] = repo_link.strip().split('/')
            if len(repo_link_parts) < 4 or repo_link_parts[2] != 'zenodo.org':
                abort(400, description='Invalid repository link (expected zenodo.org)')

            record_id: str = repo_link_parts[-1]
            url: str = f"https://zenodo.org/api/records/{record_id}/files-archive"
            response = requests.get(url)

            if response.status_code == 404:
                abort(404, description=f"Repository '{repo_link}' not found.")
            elif response.status_code != 200:
                abort(500, description=f"Failed to download repository: {response.status_code}")

            # Extract zip file
            with zipfile.ZipFile(io.BytesIO(response.content)) as zf:
                zf.extractall(DATA_DIR / experiment_id)

            # Create experiment instance
            message: str = f"Created by downloading repository from '{repo_link}'."
            experiment = cls(
                id=experiment_id,
                name=name,
                source_message=message
            )

            return cls._create_with_notebook(experiment)

        except Exception:
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
        :raises HTTPException: If the TPR file is invalid or cannot be processed.
        """
        if not tpr.filename or not tpr.filename.endswith('.tpr'):
            abort(400, description='Invalid file format (expected .tpr)')

        experiment_id: str = cls.prepare_env()

        try:
            tpr.save(DATA_DIR / experiment_id / 'input.tpr')

            message: str = f"Created by uploading TPR file '{tpr.filename}'."
            experiment = cls(
                id=experiment_id,
                name=name,
                source_message=message
            )

            return cls._create_with_notebook(experiment)

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

        # Step 2: Running simulation (experiment has a GROMACS job)
        if self.gromacs_jobs:
            return 2, 'simulating'

        # Step 2: Tuning (experiment has terminated tuner job)
        if any(j.summary.get('TERMINATED', 0) > 0 for j in self.tuner_jobs):
            return 2, 'tuning'

        # Step 1: Tuning (experiment has a tuner job)
        if self.tuner_jobs:
            return 1, 'tuning'

        # Step 1: Setup complete (directory contains a TPR file)
        if get_files_with_extensions(DATA_DIR / self.id, 'tpr'):
            return 1, 'setup complete'

        return 0, 'setup'

    def delete(self) -> None:
        """
        Delete the experiment and all its related resources.
        """

        # Delete notebook pod if it exists
        if self.notebook and self.notebook.status == PodStatus.RUNNING:
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

    def publish(self, token: str, community: str) -> dict:
        """
        Publish the experiment to MDRepo.

        Args:
            token: OAuth2 access token for MDRepo API.
            community: Community slug to publish the experiment to.

        Returns:
            Metadata of the published experiment from MDRepo.

        Raises:
            HTTPException: If the experiment cannot be published.
        """
        metadata: dict = {
            "simulations": [],
        }

        # Create experiment in MDRepo
        mdrepo_experiment = mdrepo.create_experiment(token, community, metadata)
        self.mdrepo_id = mdrepo_experiment.get('id')

        if self.mdrepo_id is None:
            abort(500, description='Failed to create experiment in MDRepo.')

        # Upload files to MDRepo
        for file in (DATA_DIR / self.id).iterdir():
            if not file.is_file():
                continue

            try:
                mdrepo.upload_file(token, self.mdrepo_id, file)
            except ValueError:
                logger.error(f"Failed to upload file {file.name} to MDRepo.", exc_info=True)

        db.session.commit()
        logger.info(f"Published experiment {self.id} to MDRepo with ID {self.mdrepo_id}")
        return mdrepo_experiment
