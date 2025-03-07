from shutil import rmtree
from dataclasses import dataclass
from werkzeug.datastructures import FileStorage

from config import DATA_DIR
from utils import get_unique_id

import uuid


@dataclass
class Experiment:
    id: str
    name: str
    status: str
    token: str = str(uuid.uuid4())
    step: int = 0


    @classmethod
    def prepare_env(cls) -> str:
        id = get_unique_id()

        # TODO: create pvc

        (DATA_DIR / id).mkdir(parents=True, exist_ok=True)
        return id


    @classmethod
    def from_pdb(cls, name: str, pdb_id: str) -> 'Experiment':
        # TODO: do something with PDB ID

        id = cls.prepare_env()
        return cls(id=id, name=name, status='setup', step=0)


    @classmethod
    def from_repo(cls, name: str, repo_link: str) -> 'Experiment':
        # TODO: do something with repo link

        id = cls.prepare_env()
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
