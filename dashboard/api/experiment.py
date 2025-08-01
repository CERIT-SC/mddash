import io
import requests
import zipfile
import logging
from uuid import uuid4
from dataclasses import dataclass, field
from shutil import rmtree
from werkzeug.datastructures import FileStorage

from config import DATA_DIR, NAMESPACE
from gromacs_job import GromacsJob
from k8s import delete_pod, delete_service
from k8s_status import PodStatus, JobStatus
from utils import get_unique_id, get_files_with_extension
import caddy_client
import tuner_client


logger = logging.getLogger(__name__)


@dataclass
class Experiment:
    # unique ID of the experiment, also used as the directory name
    id: str
    # name of the experiment
    name: str
    # message for user to understand the source of the experiment
    source_message: str
    # current step in the experiment
    step: int
    # status message of the experiment shown in the UI
    status: str
    # status of the Jupyter notebook pod
    notebook_status: PodStatus = PodStatus.UNKNOWN
    # token for accessing jupyter notebook
    token: str = field(default_factory=lambda: str(uuid4()))
    # Tuner jobs of the experiment, key is a TPR file name
    tuner_jobs: dict[str, dict] = field(default_factory=dict)
    # GROMACS jobs of the experiment, key is a TPR file name
    gromacs_jobs: dict[str, GromacsJob] = field(default_factory=dict)
    # ID of the experiment in MDRepo
    mdrepo_id: str | None = None


    def __post_init__(self):
        """Convert dictionary values to GromacsJob instances if needed"""
        for key, value in self.gromacs_jobs.items():
            if isinstance(value, dict):
                self.gromacs_jobs[key] = GromacsJob(**value)


    @classmethod
    def prepare_env(cls) -> str:
        id = get_unique_id(DATA_DIR)
        (DATA_DIR / id).mkdir(parents=True, exist_ok=True)
        return id


    @classmethod
    def from_pdb(cls, name: str, pdb_id: str) -> 'Experiment':
        id = cls.prepare_env()
        pdb_id = pdb_id.strip().upper()

        # Download PDB file
        try:
            url = f"https://files.rcsb.org/download/{pdb_id}.pdb"
            response = requests.get(url)
            
            if response.status_code == 404:
                raise ValueError(f"PDB ID '{pdb_id}' not found.")
            elif response.status_code != 200:
                raise ValueError(f"Failed to download PDB file: {response.status_code}")

            with open(DATA_DIR / id / 'input.pdb', 'wb') as f:
                f.write(response.content)
        except:
            rmtree(DATA_DIR / id)
            raise

        message = f"Created by downloading '{pdb_id}' from RCSB PDB."
        return cls(id=id, name=name, status='setup', step=0, source_message=message)


    @classmethod
    def from_repo(cls, name: str, repo_link: str) -> 'Experiment':
        id = cls.prepare_env()

        # Download repository as zip
        try:
            repo_link_parts = repo_link.strip().split('/')
            if repo_link_parts[2] != 'zenodo.org':
                raise ValueError('Invalid repository link (expected zenodo.org)')

            record_id = repo_link_parts[-1]
            url = f"https://zenodo.org/api/records/{record_id}/files-archive"
            response = requests.get(url)

            if response.status_code == 404:
                raise ValueError(f"Repository '{repo_link}' not found.")
            elif response.status_code != 200:
                raise ValueError(f"Failed to download repository: {response.status_code}")

            with zipfile.ZipFile(io.BytesIO(response.content)) as zf:
                zf.extractall(DATA_DIR / id)
        except:
            rmtree(DATA_DIR / id)
            raise

        message = f"Created by downloading repository from '{repo_link}'."
        return cls(id=id, name=name, status='setup', step=0, source_message=message)


    @classmethod
    def from_tpr(cls, name: str, tpr: FileStorage) -> 'Experiment':
        if not tpr.filename or not tpr.filename.endswith('.tpr'):
            raise ValueError('Invalid file format (expected .tpr)')

        id = cls.prepare_env()
        tpr.save(DATA_DIR / id / 'input.tpr')

        message = f"Created by uploading TPR file '{tpr.filename}'."
        return cls(id=id, name=name, status='setup complete', step=1, source_message=message)


    def delete(self) -> None:
        """
        Delete the experiment and all its related resources
        """
        # TODO: duplicated code here, use smarter resource management

        # Delete notebook pod if it exists
        if self.notebook_status == PodStatus.RUNNING:
            pod_name = f'notebook-{self.id}'
            svc_name = f'svc-{self.id}'
            route_id = f'route-{self.id}-notebook'

            try:
                delete_pod(NAMESPACE, pod_name)
            except Exception:
                logger.error(f'Failed to delete notebook pod:', exc_info=True)

            try:
                delete_service(NAMESPACE, svc_name)
            except Exception as e:
                logger.error(f'Failed to delete notebook service:', exc_info=True)

            if not caddy_client.remove_route(route_id):
                logger.error('Failed to remove route from Caddy.')

        # Delete tuner jobs
        for tuner_job in self.tuner_jobs.values():
            try:
                tuner_client.delete_job(tuner_job['tuner_run_id'])
            except Exception:
                logger.error(f'Failed to delete tuner job {tuner_job["tuner_run_id"]}:', exc_info=True)

        # Delete GROMACS jobs
        for gmx_job in self.gromacs_jobs.values():
            try:
                gmx_job.delete()
            except Exception:
                logger.error(f'Failed to delete GROMACS job {gmx_job.job_name}:', exc_info=True)

        # Delete all files in the experiment directory
        rmtree(DATA_DIR / self.id)


    def update_step(self) -> None:
        
        # Step 5: Published (experiment has mdrepo_id)
        if self.mdrepo_id:
            self.step = 5
            self.status = 'published'
            return

        # Step 4: Analyzing (experiment has terminated GROMACS job)
        if any(map(lambda j: j.status == JobStatus.TERMINATED, self.gromacs_jobs.values())):
            self.step = 4
            self.status = 'analyzing'
            return

        # NOTE: Step 3 is skipped because no action is required to progress from the Analyze step to the Publish step

        # Step 2: Running simulation (experiment has running GROMACS job)
        if any(map(lambda j: j.status == JobStatus.RUNNING, self.gromacs_jobs.values())):
            self.step = 2
            self.status = 'simulating'
            return

        # Step 2: Tuning (experiment has terminated tuner job)
        if any(map(lambda j: j.get('summary', {}).get('TERMINATED', 0) > 0, self.tuner_jobs.values())):
            self.step = 2
            self.status = 'tuning'
            return

        # Step 1: Tuning (experiment has running tuner job)
        if any(map(lambda j: j.get('summary', {}).get('RUNNING', 0) > 0, self.tuner_jobs.values())):
            self.step = 1
            self.status = 'tuning'
            return

        # Step 1: Setup complete (directory contains a TPR file)
        # TODO: user action in notebook
        if get_files_with_extension(DATA_DIR / self.id, 'tpr'):
            self.step = 1
            self.status = 'setup complete'
            return

        # Step 0: Setup
        self.step = 0
        self.status = 'setup'
