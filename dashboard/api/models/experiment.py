import io
import logging
import zipfile
from datetime import datetime
from http import HTTPStatus
from shutil import rmtree
from typing import TYPE_CHECKING

import requests
from cachetools import TTLCache, cached
from clients import mdrepo
from config import DATA_DIR, MDREPO_RECORD_NAME, MDREPO_URL
from enums import JobStatus, PodStatus
from extensions import db
from flask import session
from sqlalchemy.orm import Mapped, mapped_column, relationship
from token_manager import MDRepoTokenManager
from utils import download_git_repo, get_files_with_extensions, get_unique_id
from werkzeug.datastructures import FileStorage
from werkzeug.exceptions import BadRequest, InternalServerError, NotFound
from werkzeug.utils import secure_filename

from .notebook import Notebook

if TYPE_CHECKING:
    from .gromacs_job import GromacsJob
    from .tuner_job import TunerJob


logger = logging.getLogger(__name__)
step_status_cache: TTLCache = TTLCache(maxsize=100, ttl=0.1)  # 100ms
mdrepo_status_cache: TTLCache = TTLCache(maxsize=100, ttl=60)  # 60s


class Experiment(db.Model):  # type: ignore
    """
    SQLAlchemy model representing a molecular dynamics experiment.

    An experiment tracks the lifecycle of a simulation from initial setup
    through execution to publication. It can be created from PDB files,
    Zenodo repositories, or TPR file uploads.

    Attributes:
        id: Unique 5-character experiment identifier, also used as directory name.
        created_at: Timestamp when the experiment was created.
        updated_at: Timestamp when the experiment was last modified.
        name: Human-readable name of the experiment.
        source_message: Description of how the experiment was created.
        notebooks_repo: Git repository URL containing setup notebooks.
        mdrepo_id: MDRepo record ID if the experiment has been published.
        notebook: Associated setup notebook for this experiment.
        tuner_jobs: List of tuner jobs associated with this experiment.
        gromacs_jobs: List of GROMACS simulation jobs for this experiment.
    """

    __tablename__ = "experiments"

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
    # git repository URL containing setup notebooks (nullable for legacy experiments) TODO: make non-nullable
    notebooks_repo: Mapped[str | None] = mapped_column(db.String(512), nullable=True)
    # ID of the experiment in MDRepo
    mdrepo_id: Mapped[str | None] = mapped_column(db.String(255), nullable=True)
    # Whether the experiment is published in MDRepo (True=published, False=draft, None=not in MDRepo)
    mdrepo_published: Mapped[bool | None] = mapped_column(db.Boolean, nullable=True)

    # Setup notebook status
    notebook: Mapped["Notebook"] = relationship(
        "Notebook", back_populates="experiment", cascade="all, delete-orphan", uselist=False
    )
    # Tuner jobs of the experiment
    tuner_jobs: Mapped[list["TunerJob"]] = relationship(
        "TunerJob", back_populates="experiment", cascade="all, delete-orphan"
    )
    # GROMACS jobs of the experiment
    gromacs_jobs: Mapped[list["GromacsJob"]] = relationship(
        "GromacsJob", back_populates="experiment", cascade="all, delete-orphan"
    )

    @property
    def step(self) -> int:
        """Step of the experiment based on its current state."""
        return self._step_status()[0]

    @property
    def status(self) -> str:
        """Status of the experiment based on its current state."""
        return self._step_status()[1]

    @property
    def mdrepo_record_url(self) -> str | None:
        """Get the MDRepo record URL if published."""
        if self.mdrepo_id:
            return f"{MDREPO_URL}/{MDREPO_RECORD_NAME}/uploads/{self.mdrepo_id}"
        return None

    @classmethod
    def prepare_env(cls, notebooks_repo: str) -> str:
        """
        Prepare environment directory for new experiment.

        Creates a unique experiment directory and clones the notebooks repository into it.

        Args:
            notebooks_repo: Git repository URL containing setup notebooks.

        Returns:
            The unique experiment ID.

        Raises:
            Exception: If there is an error during environment preparation.
        """
        experiment_id: str = get_unique_id(DATA_DIR)
        experiment_dir = DATA_DIR / experiment_id
        experiment_dir.mkdir(parents=True, exist_ok=True)
        try:
            download_git_repo(notebooks_repo, experiment_dir)
        except Exception:
            rmtree(experiment_dir, ignore_errors=True)
            raise
        return experiment_id

    @classmethod
    def _create_with_notebook(cls, experiment: "Experiment") -> "Experiment":
        """
        Create experiment with auto-generated notebook.

        Args:
            experiment: The Experiment instance to create.

        Returns:
            The created Experiment instance with an associated Notebook.

        Raises:
            Exception: If there is an error during creation.
        """
        db.session.add(experiment)
        db.session.flush()

        notebook = Notebook(experiment_id=experiment.id)  # type: ignore[call-arg]
        db.session.add(notebook)
        db.session.commit()

        logger.info(f"Created experiment {experiment.id}")
        return experiment

    @classmethod
    def from_pdb(cls, name: str, pdb_id: str, notebooks_repo: str) -> "Experiment":
        """
        Create experiment from PDB ID with database persistence.

        Args:
            name: Name of the experiment.
            pdb_id: PDB ID to download (e.g., 1A2B).
            notebooks_repo: Git repository URL containing setup notebooks.

        Returns:
            The created Experiment instance.

        Raises:
            HTTPException: If the PDB ID is not found or download fails.
        """
        experiment_id: str = cls.prepare_env(notebooks_repo)
        pdb_id = pdb_id.strip().upper()

        try:
            # Download PDB file
            url: str = f"https://files.rcsb.org/download/{pdb_id}.pdb"
            response = requests.get(url, timeout=30)

            if response.status_code == HTTPStatus.NOT_FOUND:
                raise NotFound(description=f"PDB ID '{pdb_id}' not found.")
            if response.status_code != HTTPStatus.OK:
                raise InternalServerError(description=f"Failed to download PDB file: {response.status_code}")

            with (DATA_DIR / experiment_id / "input.pdb").open("wb") as f:
                f.write(response.content)

            message: str = f"Created by downloading '{pdb_id}' from RCSB PDB."
            experiment = cls(id=experiment_id, name=name, source_message=message, notebooks_repo=notebooks_repo)  # type: ignore[call-arg]

            return cls._create_with_notebook(experiment)

        except Exception:
            # Cleanup on failure
            rmtree(DATA_DIR / experiment_id, ignore_errors=True)
            db.session.rollback()
            raise

    @classmethod
    def from_repo(cls, name: str, repo_link: str, notebooks_repo: str) -> "Experiment":
        """
        Create experiment from Zenodo repository with database persistence.

        Args:
            name: Name of the experiment.
            repo_link: Zenodo repository link (e.g., https://zenodo.org/record/1234567).
            notebooks_repo: Git repository URL containing setup notebooks.

        Returns:
            The created Experiment instance.

        Raises:
            HTTPException: If the repository link is invalid or download fails.
        """
        experiment_id: str = cls.prepare_env(notebooks_repo)

        try:
            # Validate and parse repository link
            repo_link_parts: list[str] = repo_link.strip().split("/")
            # Expected format: https://zenodo.org/record/1234567
            min_zenodo_parts = 4
            if len(repo_link_parts) < min_zenodo_parts or repo_link_parts[2] != "zenodo.org":
                raise BadRequest(description="Invalid repository link (expected zenodo.org)")

            record_id: str = repo_link_parts[-1]
            url: str = f"https://zenodo.org/api/records/{record_id}/files-archive"
            response = requests.get(url, timeout=60)

            if response.status_code == HTTPStatus.NOT_FOUND:
                raise NotFound(description=f"Repository '{repo_link}' not found.")
            if response.status_code != HTTPStatus.OK:
                raise InternalServerError(description=f"Failed to download repository: {response.status_code}")

            # Extract zip file
            with zipfile.ZipFile(io.BytesIO(response.content)) as zf:
                zf.extractall(DATA_DIR / experiment_id)

            # Create experiment instance
            message: str = f"Created by downloading repository from '{repo_link}'."
            experiment = cls(id=experiment_id, name=name, source_message=message, notebooks_repo=notebooks_repo)  # type: ignore[call-arg]

            return cls._create_with_notebook(experiment)

        except Exception:
            # Cleanup on failure
            rmtree(DATA_DIR / experiment_id, ignore_errors=True)
            db.session.rollback()
            raise

    @classmethod
    def from_files(cls, name: str, files: list[FileStorage], notebooks_repo: str) -> "Experiment":
        """
        Create experiment from file uploads with database persistence.

        Args:
            name: Name of the experiment.
            files: List of uploaded files.
            notebooks_repo: Git repository URL containing setup notebooks.

        Returns:
            The created Experiment instance.

        Raises:
            HTTPException: If no files are provided or saving fails.
        """
        if not files:
            raise BadRequest(description="No files provided")

        experiment_id: str = cls.prepare_env(notebooks_repo)

        try:
            filenames = []
            for file in files:
                if not file.filename:
                    continue
                filename = secure_filename(file.filename)
                file.save(DATA_DIR / experiment_id / filename)
                filenames.append(filename)

            message: str = f"Created by uploading files: {', '.join(filenames)}."
            experiment = cls(id=experiment_id, name=name, source_message=message, notebooks_repo=notebooks_repo)  # type: ignore[call-arg]

            return cls._create_with_notebook(experiment)

        except Exception:
            # Cleanup on failure
            rmtree(DATA_DIR / experiment_id, ignore_errors=True)
            db.session.rollback()
            raise

    @cached(cache=step_status_cache)
    def _step_status(self) -> tuple[int, str]:
        """Determine (step, status) based on current state."""
        # Step 5: Published (experiment is published in MDRepo)
        if self.mdrepo_published is True:
            return 5, "published"

        # Step 5: Publishing (experiment is in MDRepo draft)
        if self.mdrepo_published is False:
            return 5, "publishing"

        # Step 4: Analyzing (experiment has terminated GROMACS job)
        if any(j.status == JobStatus.TERMINATED for j in self.gromacs_jobs):
            return 4, "analyzing"

        # Step 3: Allow user to analyze a running simulation
        if any(j.status == JobStatus.RUNNING for j in self.gromacs_jobs):
            return 3, "simulating"

        # Step 2: Running simulation (experiment has a GROMACS job)
        if self.gromacs_jobs:
            return 2, "simulating"

        # Step 2: Tuning (experiment has terminated tuner job)
        if any(j.summary.get("TERMINATED", 0) > 0 for j in self.tuner_jobs):
            return 2, "tuning"

        # Step 1: Tuning (experiment has a tuner job)
        if self.tuner_jobs:
            return 1, "tuning"

        # Step 1: Setup complete (directory contains a TPR file)
        if get_files_with_extensions(DATA_DIR / self.id, "tpr"):
            return 1, "setup complete"

        return 0, "setup"

    @cached(cache=mdrepo_status_cache, key=lambda self: self.mdrepo_id)
    def _sync_mdrepo_status(self) -> None:
        """Check if the MDRepo experiment still exists and update local database if deleted."""
        if not self.mdrepo_id:
            return

        token_manager = MDRepoTokenManager(session)
        access_token = token_manager.get_valid_token()
        if not access_token:
            return

        try:
            status = mdrepo.check_experiment_status(access_token, self.mdrepo_id)

            if status is None:
                self.mdrepo_id = None
                self.mdrepo_published = None
            else:
                self.mdrepo_published = status

            db.session.commit()
        except Exception:
            db.session.rollback()
            logger.exception(f"Failed to check MDRepo status for experiment '{self.mdrepo_id}'")

    def delete(self) -> None:
        """Delete the experiment and all its related resources."""
        # Delete notebook pod if it exists
        if self.notebook and self.notebook.status == PodStatus.RUNNING:
            self.notebook.stop()

        # Delete tuner jobs
        for tuner_job in self.tuner_jobs:
            try:
                tuner_job.delete()
            except Exception:
                logger.exception(f"Failed to delete tuner job {tuner_job.tuner_run_id}")

        # Delete GROMACS jobs
        for gmx_job in self.gromacs_jobs:
            try:
                gmx_job.delete()
            except Exception:
                logger.exception(f"Failed to delete GROMACS job {gmx_job.id}")

        # Delete all files in the experiment directory
        rmtree(DATA_DIR / self.id, ignore_errors=True)

    def publish(self, community: str) -> dict:
        """
        Publish the experiment to MDRepo into a draft state.

        Args:
            community: Community slug to publish the experiment to.

        Returns:
            Metadata of the published experiment from MDRepo.

        Raises:
            HTTPException: If the experiment cannot be published.
        """
        metadata: dict = {
            "simulations": [],
        }

        token_manager = MDRepoTokenManager(session)
        access_token = token_manager.get_valid_token()

        if not access_token:
            raise InternalServerError(
                description="No valid MDRepo access token available. Please authenticate with MDRepo."
            )

        # Create experiment in MDRepo
        mdrepo_experiment = mdrepo.create_experiment(access_token, community, metadata)
        mdrepo_id = mdrepo_experiment.get("id")

        if mdrepo_id is None:
            raise InternalServerError(description="Failed to create experiment in MDRepo.")

        self.mdrepo_id = mdrepo_id
        self.mdrepo_published = False
        db.session.commit()

        logger.info(f"Created MDRepo experiment with ID '{mdrepo_id}' for experiment '{self.id}'")

        # Start background thread (daemon) to perform uploads and return immediately
        mdrepo.start_upload_worker(access_token, experiment_id=mdrepo_id, experiment_dir=DATA_DIR / self.id)

        logger.info(f"Queued file upload job '{self.id}' to MDRepo.")
        return mdrepo_experiment
