import io
import requests
import zipfile
from uuid import uuid4
from dataclasses import dataclass, field
from shutil import rmtree
from werkzeug.datastructures import FileStorage

from config import DATA_DIR
from gromacs_job import GromacsJob
from utils import get_unique_id, get_files_with_extension


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
    # status message shown in the UI
    status: str
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
        rmtree(DATA_DIR / self.id)


    def update_step(self) -> None:
        
        # Step 5: Published (experiment has mdrepo_id)
        if self.mdrepo_id:
            self.step = 5
            self.status = 'published'
            return

        # Step 4: Analyzing (directory contains XTC file)
        if get_files_with_extension(DATA_DIR / self.id, 'xtc'):
            self.step = 4
            self.status = 'analyzing'
            return

        # Step 3: Running simulation (experiment has GROMACS jobs)
        if self.gromacs_jobs:
            self.step = 3
            self.status = 'simulating'
            return

        # Step 2: Running Tuner (experiment has Tuner jobs)
        if self.tuner_jobs:
            self.step = 2
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
