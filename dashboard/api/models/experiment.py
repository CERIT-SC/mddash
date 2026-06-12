import logging
import tempfile
import threading
import zipfile
from datetime import UTC, datetime
from http import HTTPStatus
from pathlib import Path
from shutil import move, rmtree
from typing import TYPE_CHECKING
from urllib.parse import urlparse

import requests
import yaml
from cache import mdrepo_status_cache, step_status_cache
from cachetools import cached
from clients import mdposit, mdrepo, metadump
from config import API_PREFIX, DATA_DIR, MDPOSIT_VRE_LITE_URL, MDREPO_RECORD_NAME, MDREPO_URL
from enums import Engine, JobStatus, PodStatus
from extensions import db
from flask import session
from sqlalchemy.orm import Mapped, mapped_column, relationship
from token_manager import MDRepoTokenManager
from utils import download_git_repo, get_files_with_extensions, get_unique_id
from validators import check_path
from werkzeug.datastructures import FileStorage
from werkzeug.exceptions import BadRequest, InternalServerError, NotFound
from werkzeug.utils import secure_filename

from .notebook import Notebook

if TYPE_CHECKING:
    from .analysis_job import AnalysisJob
    from .simulation_job import SimulationJob
    from .tuner_job import TunerJob


logger = logging.getLogger(__name__)


def _resolve_repo_link(repo_link: str) -> str:
    resolved = repo_link.strip().rstrip("/")
    if urlparse(resolved).netloc == "doi.org":
        response = requests.head(resolved, allow_redirects=True, timeout=30)
        resolved = response.url.rstrip("/")

    return resolved


def _safe_extract_zip(zf: zipfile.ZipFile, output_dir: Path) -> None:
    resolved_output_dir = output_dir.resolve()
    for member in zf.infolist():
        output_path = (output_dir / member.filename).resolve()
        try:
            output_path.relative_to(resolved_output_dir)
        except ValueError as exc:
            raise BadRequest(description=f"Unsafe path in repository archive: {member.filename}") from exc

        zf.extract(member, output_dir)


def _import_invenio_repo(repo_link: str, experiment_id: str) -> None:
    # Parse InvenioRDM-compatible URL (Zenodo, MDRepo, etc.)
    # UI URL format:  {scheme}://{host}/[collection/]records/{id}
    # API URL format: {scheme}://{host}/api/{collection_or_records}/{id}/files-archive
    parsed = urlparse(repo_link)
    path_parts = [p for p in parsed.path.split("/") if p]
    record_id: str = path_parts[-1]
    records_idx: int = path_parts.index("records")  # raises ValueError if missing
    prefix_parts: list[str] = path_parts[:records_idx]
    api_segment: str = "/".join(prefix_parts) if prefix_parts else "records"
    url: str = f"{parsed.scheme}://{parsed.netloc}/api/{api_segment}/{record_id}/files-archive"

    with tempfile.NamedTemporaryFile(suffix=".zip") as tmp_file:
        tmp_path = Path(tmp_file.name)
        with requests.get(url, stream=True, timeout=300) as response:
            if response.status_code == HTTPStatus.NOT_FOUND:
                raise NotFound(description=f"Repository '{repo_link}' not found.")
            if response.status_code != HTTPStatus.OK:
                raise InternalServerError(description=f"Failed to download repository: {response.status_code}")

            # 128KB chunk size for better performance with large files
            for chunk in response.iter_content(chunk_size=128 * 1024):
                tmp_file.write(chunk)

        tmp_file.flush()
        with zipfile.ZipFile(tmp_path) as zf:
            _safe_extract_zip(zf, DATA_DIR / experiment_id)


def _import_mdposit_repo(repo_link: str, experiment_id: str) -> None:
    accession = mdposit.extract_accession(repo_link)
    if not accession:
        raise BadRequest(description="Missing MDPosit project accession.")

    output_dir = DATA_DIR / experiment_id
    output_dir.mkdir(parents=True, exist_ok=True)

    try:
        mdposit.get_project(accession)
        with tempfile.TemporaryDirectory(dir=output_dir) as tmp_dir_name:
            tmp_dir = Path(tmp_dir_name)
            downloaded_paths = mdposit.download_project(accession, tmp_dir)
            resolved_tmp_dir = tmp_dir.resolve()

            for downloaded_path in downloaded_paths:
                source_path = Path(downloaded_path)
                relative_path = source_path.resolve().relative_to(resolved_tmp_dir)
                destination_path = output_dir / relative_path
                destination_path.parent.mkdir(parents=True, exist_ok=True)
                move(source_path, destination_path)
    except ValueError as exc:
        raise BadRequest(description=str(exc)) from exc
    except requests.HTTPError as exc:
        raise InternalServerError(description=f"Failed to download MDPosit project: {exc}") from exc


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
        engine: Molecular dynamics engine (GMX or AMBER).
        notebook: Associated setup notebook for this experiment.
        tuner_jobs: List of tuner jobs associated with this experiment.
        simulation_jobs: List of simulation jobs for this experiment.
    """

    __tablename__ = "experiments"

    # unique ID of the experiment, also used as the directory name
    id: Mapped[str] = mapped_column(db.String(5), primary_key=True)
    # creation time
    created_at: Mapped[datetime] = mapped_column(db.DateTime, default=lambda: datetime.now(UTC))
    # last modification time
    updated_at: Mapped[datetime] = mapped_column(
        db.DateTime,
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
    )

    # name of the experiment
    name: Mapped[str] = mapped_column(db.String(255), nullable=False)
    # message for user to understand the source of the experiment
    source_message: Mapped[str | None] = mapped_column(db.Text, nullable=False)
    # git repository URL containing setup notebooks (nullable for legacy experiments) TODO: make non-nullable (breaks db migration)
    notebooks_repo: Mapped[str | None] = mapped_column(db.String(512), nullable=True)
    # ID of the experiment in MDRepo
    mdrepo_id: Mapped[str | None] = mapped_column(db.String(255), nullable=True)
    # Whether the experiment is published in MDRepo (True=published, False=draft, None=not in MDRepo)
    mdrepo_published: Mapped[bool | None] = mapped_column(db.Boolean, nullable=True)
    # Molecular dynamics engine (GMX or AMBER)
    engine: Mapped[Engine] = mapped_column(db.Enum(Engine), nullable=False, default=Engine.GMX)

    # Setup notebook status
    notebook: Mapped["Notebook"] = relationship(
        "Notebook", back_populates="experiment", cascade="all, delete-orphan", uselist=False
    )
    # Tuner jobs of the experiment
    tuner_jobs: Mapped[list["TunerJob"]] = relationship(
        "TunerJob", back_populates="experiment", cascade="all, delete-orphan"
    )
    # Simulation jobs of the experiment (base relationship for JTI)
    simulation_jobs: Mapped[list["SimulationJob"]] = relationship(
        "SimulationJob", back_populates="experiment", cascade="all, delete-orphan"
    )
    # Analysis jobs of the experiment
    analysis_jobs: Mapped[list["AnalysisJob"]] = relationship(
        "AnalysisJob", back_populates="experiment", cascade="all, delete-orphan"
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
        """The MDRepo record URL if published."""
        if self.mdrepo_id:
            return f"{MDREPO_URL}/{MDREPO_RECORD_NAME}/uploads/{self.mdrepo_id}"
        return None

    @classmethod
    def prepare_env(cls, notebooks_repo: str, access_token: str | None = None) -> str:
        """
        Prepare environment directory for new experiment.

        Creates a unique experiment directory and clones the notebooks repository into it.

        Args:
            notebooks_repo: Git repository URL containing setup notebooks.
            access_token: Optional GitHub access token for private repositories.

        Returns:
            The unique experiment ID.
        """
        experiment_id: str = get_unique_id(DATA_DIR)
        experiment_dir = DATA_DIR / experiment_id
        experiment_dir.mkdir(parents=True, exist_ok=True)
        try:
            download_git_repo(notebooks_repo, experiment_dir, access_token)
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
        """
        db.session.add(experiment)
        db.session.flush()

        notebook = Notebook(experiment_id=experiment.id)  # type: ignore[call-arg]
        db.session.add(notebook)
        db.session.commit()

        logger.info(f"Created experiment {experiment.id}")
        return experiment

    @classmethod
    def from_pdb(
        cls,
        name: str,
        pdb_id: str,
        notebooks_repo: str,
        access_token: str | None = None,
        engine: Engine = Engine.GMX,
    ) -> "Experiment":
        """
        Create experiment from PDB ID with database persistence.

        Args:
            name: Name of the experiment.
            pdb_id: PDB ID to download (e.g., 1A2B).
            notebooks_repo: Git repository URL containing setup notebooks.
            access_token: Optional GitHub access token for private repositories.
            engine: Molecular dynamics engine (default: GMX).

        Returns:
            The created Experiment instance.

        Raises:
            NotFound: If the PDB ID is not found.
            InternalServerError: If the PDB file download fails.
        """
        experiment_id: str = cls.prepare_env(notebooks_repo, access_token)
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
            experiment = cls(
                id=experiment_id, name=name, source_message=message, notebooks_repo=notebooks_repo, engine=engine
            )

            return cls._create_with_notebook(experiment)

        except Exception:
            # Cleanup on failure
            rmtree(DATA_DIR / experiment_id, ignore_errors=True)
            db.session.rollback()
            raise

    @classmethod
    def from_repo(
        cls,
        name: str,
        repo_link: str,
        notebooks_repo: str,
        access_token: str | None = None,
        engine: Engine = Engine.GMX,
    ) -> "Experiment":
        """
        Create experiment from a supported repository URL.

        Args:
            name: Name of the experiment.
            repo_link: Repository record URL.
            notebooks_repo: Git repository URL containing setup notebooks.
            access_token: Optional GitHub access token for private repositories.
            engine: Molecular dynamics engine (default: GMX).

        Returns:
            The created Experiment instance.
        """
        experiment_id: str = cls.prepare_env(notebooks_repo, access_token)

        try:
            resolved_repo_link = _resolve_repo_link(repo_link)
            if mdposit.is_mdposit_url(resolved_repo_link):
                _import_mdposit_repo(resolved_repo_link, experiment_id)
            else:
                _import_invenio_repo(resolved_repo_link, experiment_id)

            message: str = f"Created by downloading repository from '{repo_link}'."
            experiment = cls(
                id=experiment_id, name=name, source_message=message, notebooks_repo=notebooks_repo, engine=engine
            )

            return cls._create_with_notebook(experiment)

        except Exception:
            # Cleanup on failure
            rmtree(DATA_DIR / experiment_id, ignore_errors=True)
            db.session.rollback()
            raise

    @classmethod
    def from_files(
        cls,
        name: str,
        files: list[FileStorage],
        notebooks_repo: str,
        access_token: str | None = None,
        engine: Engine = Engine.GMX,
    ) -> "Experiment":
        """
        Create experiment from file uploads with database persistence.

        Args:
            name: Name of the experiment.
            files: List of uploaded files.
            notebooks_repo: Git repository URL containing setup notebooks.
            access_token: Optional GitHub access token for private repositories.
            engine: Molecular dynamics engine (default: GMX).

        Returns:
            The created Experiment instance.

        Raises:
            BadRequest: If no files are provided.
        """
        if not files:
            raise BadRequest(description="No files provided")

        experiment_id: str = cls.prepare_env(notebooks_repo, access_token)

        try:
            filenames = []
            for file in files:
                if not file.filename:
                    continue
                filename = secure_filename(file.filename)
                file.save(DATA_DIR / experiment_id / filename)
                filenames.append(filename)

            message: str = f"Created by uploading files: {', '.join(filenames)}."
            experiment = cls(
                id=experiment_id, name=name, source_message=message, notebooks_repo=notebooks_repo, engine=engine
            )

            return cls._create_with_notebook(experiment)

        except Exception:
            # Cleanup on failure
            rmtree(DATA_DIR / experiment_id, ignore_errors=True)
            db.session.rollback()
            raise

    def _has_setup_files(self) -> bool:
        """
        Check if the experiment directory contains required setup files for the configured engine.

        Returns:
            True if all required files for the engine are present, False otherwise.
        """
        exp_dir = DATA_DIR / self.id
        if not exp_dir.exists():
            return False

        if self.engine == Engine.GMX:
            return bool(get_files_with_extensions(exp_dir, "tpr"))

        if self.engine == Engine.AMBER:
            has_mdin = get_files_with_extensions(exp_dir, "mdin")
            has_prmtop = get_files_with_extensions(exp_dir, ["prmtop", "parm7"])
            has_inpcrd = get_files_with_extensions(exp_dir, ["inpcrd", "rst7", "nc"])
            return bool(has_mdin and has_prmtop and has_inpcrd)

        return False

    @cached(cache=step_status_cache)
    def _step_status(self) -> tuple[int, str]:
        """
        Determine (step, status) based on current state.

        Returns:
            A tuple of (step, status) where step is an integer (0-5) and status
            is a string describing the current phase.
        """
        # Step 5: Published (experiment is published in MDRepo)
        if self.mdrepo_published is True:
            return 5, "published"

        # Step 5: Publishing (experiment is in MDRepo draft)
        if self.mdrepo_published is False:
            return 5, "publishing"

        # Step 4: Analyzing (experiment has terminated simulation job)
        if any(j.status == JobStatus.TERMINATED for j in self.simulation_jobs):
            return 4, "analyzing"

        # Step 3: Allow user to analyze a running simulation
        if any(j.status == JobStatus.RUNNING for j in self.simulation_jobs):
            return 3, "simulating"

        # Step 2: Running simulation (experiment has a simulation job)
        if self.simulation_jobs:
            return 2, "simulating"

        # Step 2: Tuning (experiment has terminated tuner trial)
        if any(any(t.get("performance") is not None for t in j.trials) for j in self.tuner_jobs):
            return 2, "tuning"

        # Step 1: Tuning (experiment has a tuner job)
        if self.tuner_jobs:
            return 1, "tuning"

        # Step 1: Setup complete (directory contains required files for the engine)
        if self._has_setup_files():
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
                logger.exception(f"Failed to delete tuner job {tuner_job.id}")

        # Delete simulation jobs
        for sim_job in self.simulation_jobs:
            try:
                sim_job.delete()
            except Exception:
                logger.exception(f"Failed to delete simulation job {sim_job.id}")

        def del_dir(dir: Path) -> None:
            try:
                rmtree(dir, ignore_errors=True)
                logger.info(f"Deleted experiment directory: {dir}")
            except Exception:
                logger.exception(f"Failed to delete experiment directory {dir}")

        thread = threading.Thread(target=del_dir, args=(DATA_DIR / self.id,), daemon=True)
        thread.start()

    def publish(
        self,
        community: str = "ceitec",
        target: str = "invenio",
        selected_files: dict[str, str] | None = None,
    ) -> dict:
        """
        Publish the experiment to the selected target.

        Returns:
            Publication metadata for the selected target.

        Raises:
            BadRequest: If the publish target is unknown.
        """
        if target == "invenio":
            return self._publish_invenio(community)
        if target == "mdposit":
            return self._publish_mdposit(selected_files or {})
        raise BadRequest(description=f"Unknown publish target: {target}")

    def _publish_invenio(self, community: str) -> dict:
        """
        Publish the experiment to MDRepo into a draft state.

        Args:
            community: Community slug to publish the experiment to.

        Returns:
            Metadata of the published experiment from MDRepo.

        Raises:
            InternalServerError: If there is no valid access token or MDRepo creation fails.
        """
        token_manager = MDRepoTokenManager(session)
        access_token = token_manager.get_valid_token()

        if not access_token:
            raise InternalServerError(
                description="No valid MDRepo access token available. Please authenticate with MDRepo."
            )

        gmx_jobs = [j for j in self.simulation_jobs if j.engine == Engine.GMX]
        tpr_paths = [DATA_DIR / self.id / j.tpr_name for j in gmx_jobs]
        simulations = metadump.extract_metadata_bulk(tpr_paths) if tpr_paths else []

        metadata: dict = {"simulations": simulations}

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

    def _publish_mdposit(self, selected_files: dict[str, str]) -> dict:
        """
        Prepare stateless MDPosit publication metadata for selected experiment files.

        Returns:
            Metadata file and selected file descriptors for MDPosit publishing.

        Raises:
            BadRequest: If required selected files are missing or invalid.
            InternalServerError: If metadata generation fails.
        """
        exp_dir = DATA_DIR / self.id
        if not exp_dir.exists():
            raise BadRequest(description="Experiment directory not found.")
        exp_dir_resolved = exp_dir.resolve()

        allowed_extensions = {
            "structure": {"pdb", "gro"},
            "topology": {"top", "prmtop", "parm7", "psf"},
            "trajectory": {"xtc", "trr", "nc", "dcd"},
        }

        files: list[dict[str, str]] = []
        selected_paths: dict[str, Path] = {}

        for role, extensions in allowed_extensions.items():
            relative_path = selected_files.get(role)
            if not relative_path:
                raise BadRequest(description=f"Missing required file for role: {role}")

            check_path(relative_path, exp_dir)
            try:
                file_path = (exp_dir / relative_path).resolve()
                file_path.relative_to(exp_dir_resolved)
            except (OSError, ValueError):
                raise BadRequest(description=f"Selected file for role '{role}' is invalid.")

            if not file_path.is_file():
                raise BadRequest(description=f"Selected file for role '{role}' does not exist.")

            extension = file_path.suffix.lstrip(".").lower()
            if extension not in extensions:
                allowed = ", ".join(sorted(extensions))
                raise BadRequest(description=f"Invalid file extension for role '{role}'. Allowed: {allowed}")

            selected_paths[role] = file_path
            files.append({
                "role": role,
                "path": relative_path,
                "url": f"{API_PREFIX}/experiments/{self.id}/files/{relative_path}",
            })

        metadata = self._build_mdposit_metadata(selected_paths)
        metadata_file = exp_dir / "inputs.yaml"
        metadata_relative_path = str(metadata_file.relative_to(exp_dir))

        try:
            metadata_file.write_text(yaml.safe_dump(metadata, sort_keys=False), encoding="utf-8")
        except OSError as exc:
            raise InternalServerError(description=f"Failed to generate metadata file: {exc}") from exc

        return {
            "metadata_file": {
                "path": metadata_relative_path,
                "url": f"{API_PREFIX}/experiments/{self.id}/files/{metadata_relative_path}",
            },
            "files": files,
            "vre_lite_url": MDPOSIT_VRE_LITE_URL or None,
        }

    def _build_mdposit_metadata(self, selected_paths: dict[str, Path]) -> dict:
        """
        Build MDDB-compatible inputs.yaml metadata dict.

        Only fields we can determine without external assumptions are included.
        The user fills remaining fields in VRE Lite.

        Returns:
            Dictionary of metadata fields for the inputs.yaml file.
        """
        structure_name = selected_paths["structure"].name
        topology_name = selected_paths["topology"].name
        trajectory_name = selected_paths["trajectory"].name
        program = "GROMACS" if self.engine == Engine.GMX else "AMBER" if self.engine == Engine.AMBER else ""

        return {
            "name": self.name,
            "description": self.source_message or "",
            **({"program": program} if program else {}),
            "type": "trajectory",
            "method": "Classical MD",
            "input_structure_filepath": structure_name,
            "input_topology_filepath": topology_name,
            "input_trajectory_filepaths": [trajectory_name],
            "mds": [
                {
                    "name": "simulation",
                    "input_structure_filepath": structure_name,
                    "input_topology_filepath": topology_name,
                    "input_trajectory_filepaths": [trajectory_name],
                }
            ],
        }
