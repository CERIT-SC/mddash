from shutil import rmtree
from dataclasses import dataclass, field
from werkzeug.datastructures import FileStorage
import requests
import zipfile
import io

from config import DATA_DIR
from utils import get_unique_id

import uuid


@dataclass
class Experiment:
    # unique ID of the experiment, also used as the directory name
    id: str
    # name of the experiment
    name: str
    # status message shown in the UI
    status: str
    # token for accessing jupyter notebook
    token: str = str(uuid.uuid4())
    # current step in the experiment
    step: int = 0
    # Tuner jobs of the experiment, key is a TPR file name
    tuner_jobs: dict[str, dict] = field(default_factory=dict)
    # ID of the experiment in MDRepo
    mdrepo_id: str | None = None


    @classmethod
    def prepare_env(cls) -> str:
        id = get_unique_id()
        (DATA_DIR / id).mkdir(parents=True, exist_ok=True)

        # TODO: copy jupyter notebook

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

        return cls(id=id, name=name, status='setup', step=0)


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

        return cls(id=id, name=name, status='setup', step=0)


    @classmethod
    def from_tpr(cls, name: str, tpr: FileStorage) -> 'Experiment':
        if not tpr.filename.endswith('.tpr'):
            raise ValueError('Invalid file format (expected .tpr)')

        id = cls.prepare_env()
        tpr.save(DATA_DIR / id / 'input.tpr')

        return cls(id=id, name=name, status='setup complete', step=1)


    def delete(self) -> None:
        rmtree(DATA_DIR / self.id)
