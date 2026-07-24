import logging
import threading
from datetime import UTC, datetime
from http import HTTPStatus
from pathlib import Path
from shutil import rmtree
from typing import TYPE_CHECKING
from urllib.parse import quote, urlparse

import yaml
from cache import mdrepo_status_cache, step_status_cache
from cachetools import cached
from clients import mdposit, mdrepo, metadump
from config import (
    API_PREFIX,
    DATA_DIR,
    MDPOSIT_URL,
    MDPOSIT_VRE_LITE_URL,
    MDREPO_API_URL,
    MDREPO_CLIENT_ID,
    MDREPO_CLIENT_SECRET,
    MDREPO_RECORD_NAME,
    MDREPO_TOKEN_URL,
    MDREPO_URL,
)
from enums import Engine, JobStatus, PodStatus
from extensions import db
from flask import session
from notebook_modules import NotebookModule
from sqlalchemy.orm import Mapped, mapped_column, relationship
from token_manager import MDRepoTokenManager
from upload.status import (
    REASON_JOB_MISSING,
    UploadState,
    read_status,
)
from upload.submission import (
    delete_upload_resources,
    is_upload_active,
    submit_upload_job,
)
from utils import download_git_repo, download_git_repo_module, get_unique_id
from validators import validate_http_url
from werkzeug.datastructures import FileStorage
from werkzeug.exceptions import BadRequest, Conflict, InternalServerError, NotFound
from werkzeug.utils import secure_filename

from .experiment_sources import (
    chmod_schema_files_readonly,
    fetch_pdb,
    import_invenio_repo,
    import_mdposit_repo,
    list_simulations,
    resolve_repo_link,
    validate_pdb_content,
)
from .notebook import Notebook

if TYPE_CHECKING:
    from .analysis_job import AnalysisJob
    from .simulation_job import SimulationJob
    from .tuner_job import TunerJob


logger = logging.getLogger(__name__)


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
    def prepare_env(
        cls,
        notebooks_repo: str,
        access_token: str | None = None,
        notebook_module: NotebookModule | None = None,
    ) -> str:
        """
        Create a unique experiment directory and populate it with notebooks.

        Curated mode (``notebook_module`` set) sparse-checks out the module (root-path
        ``"."`` uses full clone); custom mode clones the whole repository.

        Returns:
            The unique experiment ID.
        """
        experiment_id: str = get_unique_id(DATA_DIR)
        experiment_dir = DATA_DIR / experiment_id
        experiment_dir.mkdir(parents=True, exist_ok=True)
        try:
            if notebook_module is not None:
                if notebook_module.is_root:
                    download_git_repo(notebooks_repo, experiment_dir, access_token)
                else:
                    download_git_repo_module(notebooks_repo, notebook_module.path, experiment_dir, access_token)
            else:
                download_git_repo(notebooks_repo, experiment_dir, access_token)
        except Exception:
            rmtree(experiment_dir, ignore_errors=True)
            raise

        chmod_schema_files_readonly(experiment_dir)
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
        pdb_source: str,
        notebooks_repo: str,
        access_token: str | None = None,
        engine: Engine = Engine.GMX,
        notebook_module: NotebookModule | None = None,
    ) -> "Experiment":
        """
        Create experiment from a PDB ID or a direct URL to a PDB file.

        A value without a URL scheme (e.g. ``1A2B``) is treated as an RCSB PDB ID
        and downloaded from ``files.rcsb.org``. A value with a URL scheme (e.g.
        ``https://...``) is treated as a direct URL to a PDB file and fetched
        as-is; only ``http`` and ``https`` schemes are accepted.

        Args:
            name: Name of the experiment.
            pdb_source: PDB ID (e.g., 1A2B) or a direct URL to a PDB file.
            notebooks_repo: Git repository URL containing setup notebooks.
            access_token: Optional access token for private repositories.
            engine: Molecular dynamics engine (default: GMX).
            notebook_module: Optional curated module for selective checkout.

        Returns:
            The created Experiment instance.

        Raises:
            NotFound: If the PDB ID or URL is not found.
            InternalServerError: If the PDB file download fails.
        """
        experiment_id: str = cls.prepare_env(notebooks_repo, access_token, notebook_module)
        source = pdb_source.strip()
        is_url = bool(urlparse(source).scheme)

        try:
            if is_url:
                url: str = validate_http_url(source)
                message: str = f"Created by downloading PDB file from '{source}'."
            else:
                pdb_id = source.upper()
                url = f"https://files.rcsb.org/download/{pdb_id}.pdb"
                message = f"Created by downloading '{pdb_id}' from RCSB PDB."

            # Download PDB file
            response = fetch_pdb(url)

            if response.status_code == HTTPStatus.NOT_FOUND:
                raise NotFound(description=f"PDB source '{source}' not found.")
            if response.status_code != HTTPStatus.OK:
                raise InternalServerError(description=f"Failed to download PDB file: {response.status_code}")

            validate_pdb_content(response.content)

            with (DATA_DIR / experiment_id / "input.pdb").open("wb") as f:
                f.write(response.content)

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
        notebook_module: NotebookModule | None = None,
    ) -> "Experiment":
        """
        Create experiment from a supported repository URL.

        Args:
            name: Name of the experiment.
            repo_link: Repository record URL.
            notebooks_repo: Git repository URL containing setup notebooks.
            access_token: Optional access token for private repositories.
            engine: Molecular dynamics engine (default: GMX).
            notebook_module: Optional curated module for selective checkout.

        Returns:
            The created Experiment instance.
        """
        experiment_id: str = cls.prepare_env(notebooks_repo, access_token, notebook_module)

        try:
            resolved_repo_link = resolve_repo_link(repo_link)
            if mdposit.is_mdposit_url(resolved_repo_link):
                import_mdposit_repo(resolved_repo_link, experiment_id)
            else:
                import_invenio_repo(resolved_repo_link, experiment_id)

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
        notebook_module: NotebookModule | None = None,
    ) -> "Experiment":
        """
        Create experiment from file uploads with database persistence.

        Args:
            name: Name of the experiment.
            files: List of uploaded files.
            notebooks_repo: Git repository URL containing setup notebooks.
            access_token: Optional access token for private repositories.
            engine: Molecular dynamics engine (default: GMX).
            notebook_module: Optional curated module for selective checkout.

        Returns:
            The created Experiment instance.

        Raises:
            BadRequest: If no files are provided.
        """
        if not files:
            raise BadRequest(description="No files provided")

        experiment_id: str = cls.prepare_env(notebooks_repo, access_token, notebook_module)

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
        Return whether at least one valid simulation manifest exists for the engine.

        Returns:
            True if a valid simulation exists, False otherwise.
        """
        from .simulation import Simulation  # ruff:ignore[import-outside-top-level]

        for f in Simulation.list_files(self.id):
            sim = Simulation._from_file(self.id, f.path)  # ruff:ignore[private-member-access]
            if sim.valid and sim.engine == self.engine.value:
                return True
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
        """
        Delete the experiment and all its related resources.

        Raises:
            Conflict: If an MDRepo upload is queued or running.
        """
        # Reject deletion while an upload is active (check PVC + live Job).
        upload_state = self._read_upload_state()
        if upload_state in UploadState.active():
            raise Conflict(
                description="Cannot delete experiment during active MDRepo upload. "
                "Wait for completion or retry after failure."
            )
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
        simulation_path: str | None = None,
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
            return self._publish_mdposit(simulation_path or "")
        raise BadRequest(description=f"Unknown publish target: {target}")

    def _publish_invenio(self, community: str) -> dict:
        """Publish to MDRepo as a draft and start a durable upload Job (idempotent: returns existing active upload)."""
        token_manager = MDRepoTokenManager(session)
        access_token = token_manager.get_valid_token()

        if not access_token:
            raise InternalServerError(
                description="No valid MDRepo access token available. Please authenticate with MDRepo."
            )

        # A published record cannot be retried as a draft upload.
        if self.mdrepo_published is True:
            raise Conflict(description="Experiment is already published. Cannot retry as draft upload.")

        upload_state = self._read_upload_state()

        # Skip retry only when a completed upload still has a live draft.
        if upload_state == UploadState.COMPLETED.value and self.mdrepo_id:
            raise Conflict(description="Upload already completed. Use MDRepo to view or edit the published record.")

        # If an upload is already active, return it (idempotent retry).
        if upload_state in UploadState.active():
            status = read_status(self.id, DATA_DIR)
            return {
                "id": self.mdrepo_id or "",
                "links": {},
                "upload_id": status.attempt_id if status else "",
                "upload_state": upload_state,
                "draft_url": self.mdrepo_record_url,
            }

        # If a previous attempt failed, clean up its K8s resources before retrying.
        if upload_state == UploadState.FAILED.value:
            delete_upload_resources(self.id)

        # Reuse the draft only if it still exists — the user may have deleted it in MDRepo.
        if self.mdrepo_id and mdrepo.check_experiment_status(access_token, self.mdrepo_id) is not None:
            mdrepo_id = self.mdrepo_id
            mdrepo_experiment: dict = {"id": mdrepo_id, "links": {}}
        else:
            self.mdrepo_id = None
            self.mdrepo_published = None
            mdrepo_experiment = self._create_draft(access_token, community)
            mdrepo_id = self.mdrepo_id or ""

        if not mdrepo_id:
            raise InternalServerError(description="Failed to create experiment in MDRepo.")

        # Submit the upload Job: writes queued status, creates Secret+Job, waits for admission.
        attempt_id = submit_upload_job(
            experiment_id=self.id,
            mdrepo_id=mdrepo_id,
            credential_data={
                "access_token": access_token,
                "refresh_token": session.get("mdrepo_refresh_token", ""),
                "expires_at": str(session.get("mdrepo_token_expires_at", 0)),
                "client_id": MDREPO_CLIENT_ID,
                "client_secret": MDREPO_CLIENT_SECRET,
                "api_url": MDREPO_API_URL,
                "record_name": MDREPO_RECORD_NAME,
                "token_url": MDREPO_TOKEN_URL,
            },
            data_dir=DATA_DIR,
        )

        logger.info("Durable upload Job submitted for experiment %s (attempt %s)", self.id, attempt_id)
        return {
            "id": mdrepo_id,
            "links": mdrepo_experiment.get("links", {}),
            "upload_id": attempt_id,
            "upload_state": UploadState.QUEUED.value,
            "draft_url": self.mdrepo_record_url,
        }

    def _create_draft(self, access_token: str, community: str) -> dict:
        """Create a new Invenio draft and persist its ID."""
        gmx_simulations = [s for s in list_simulations(self.id) if s.engine == Engine.GMX.value and s.valid]
        tpr_paths = []
        for sim in gmx_simulations:
            topology = sim.resolved_files.get("topology")
            if topology:
                tpr_paths.append(DATA_DIR / self.id / topology)
        simulations = metadump.extract_metadata_bulk(tpr_paths) if tpr_paths else []

        mdrepo_experiment = mdrepo.create_experiment(access_token, community, {"simulations": simulations})
        mdrepo_id = mdrepo_experiment.get("id")
        if mdrepo_id is None:
            raise InternalServerError(description="Failed to create experiment in MDRepo.")

        self.mdrepo_id = mdrepo_id
        self.mdrepo_published = False
        db.session.commit()

        logger.info("Created MDRepo experiment with ID '%s' for experiment '%s'", mdrepo_id, self.id)
        return mdrepo_experiment

    def _read_upload_state(self) -> str | None:
        """Reconcile upload state from the PVC status file and live Job (reports failed/job_missing if the Job is gone)."""
        status = read_status(self.id, DATA_DIR)
        if status is None:
            return None

        if status.state in UploadState.terminal():
            return status.state

        if status.state in UploadState.active() and not is_upload_active(self.id):
            return UploadState.FAILED.value

        return status.state

    def get_publish_status(self) -> dict:
        """Return the durable MDRepo upload status, merging the PVC document with live Job state."""
        status = read_status(self.id, DATA_DIR)

        # Resolve the effective state (may differ from the file if Job is gone).
        effective_state = self._read_upload_state()

        result: dict = {
            "experiment_id": self.id,
            "mdrepo_id": self.mdrepo_id,
            "draft_url": self.mdrepo_record_url,
            "upload_state": effective_state,
            "reason": None,
            "total_files": 0,
            "completed_files": 0,
            "total_bytes": 0,
            "completed_bytes": 0,
            "failed_files": [],
        }

        if status is not None:
            result["upload_attempt_id"] = status.attempt_id
            # If the state was overridden (job_missing), reflect that.
            if effective_state == UploadState.FAILED.value and status.state in UploadState.active():
                result["reason"] = REASON_JOB_MISSING
            else:
                result["reason"] = status.reason
            result["total_files"] = status.total_files
            result["completed_files"] = status.completed_files
            result["total_bytes"] = status.total_bytes
            result["completed_bytes"] = status.completed_bytes
            result["failed_files"] = [{"key": f.key, "error": f.error} for f in status.failed_files]

        return result

    def _publish_mdposit(self, simulation_path: str) -> dict:
        """
        Prepare stateless MDPosit publication metadata from a simulation manifest.

        Returns:
            Metadata file and selected file descriptors for MDPosit publishing.

        Raises:
            BadRequest: If MDPosit is unconfigured or required files are missing/invalid.
            InternalServerError: If metadata generation fails.
        """
        if not MDPOSIT_URL:
            raise BadRequest(description="MDPosit is not configured. Set MDPOSIT_URL to enable MDPosit publishing.")

        from .simulation import Simulation  # ruff:ignore[import-outside-top-level]

        simulation = Simulation.get(self.id, simulation_path)
        simulation.require_files(["reference_structure", "run_input", "trajectory"])

        exp_dir = DATA_DIR / self.id
        if not exp_dir.exists():
            raise BadRequest(description="Experiment directory not found.")
        exp_dir_resolved = exp_dir.resolve()

        publish_roles = {
            "reference_structure": ("structure", {"pdb", "gro"}),
            "run_input": ("topology", {"top", "prmtop", "parm7", "psf", "tpr"}),
            "trajectory": ("trajectory", {"xtc", "trr", "nc", "dcd"}),
        }

        files: list[dict[str, str]] = []
        selected_paths: dict[str, Path] = {}

        for manifest_role, (publish_role, exts) in publish_roles.items():
            if manifest_role not in simulation.files:
                raise BadRequest(description=f"Simulation is missing file role '{manifest_role}' for MDPosit.")

            file_path = simulation.resolve_role(manifest_role)
            if not file_path.is_file():
                raise BadRequest(description=f"Selected file for role '{manifest_role}' does not exist.")

            extension = file_path.suffix.lstrip(".").lower()
            if extension not in exts:
                allowed = ", ".join(sorted(exts))
                raise BadRequest(description=f"Invalid file extension for role '{manifest_role}'. Allowed: {allowed}")

            relative_path = str(file_path.relative_to(exp_dir_resolved))
            selected_paths[publish_role] = file_path
            files.append({
                "role": publish_role,
                "path": relative_path,
                "url": self._file_download_url(relative_path),
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
                "url": self._file_download_url(metadata_relative_path),
            },
            "files": files,
            "vre_lite_url": MDPOSIT_VRE_LITE_URL or None,
        }

    def _file_download_url(self, relative_path: str) -> str:
        """
        Build a URL-encoded download link for a file relative to the experiment directory.

        Returns:
            Absolute API URL with each path segment percent-encoded.
        """
        quoted = "/".join(quote(part) for part in Path(relative_path).parts if part)
        return f"{API_PREFIX}/experiments/{self.id}/files/{quoted}"

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

        metadata: dict[str, object] = {
            "name": self.name,
            **({"description": self.source_message} if self.source_message else {}),
            **({"program": program} if program else {}),
            "type": "trajectory",
            "method": "Classical MD",
            "input_structure_filepath": structure_name,
            "input_topology_filepath": topology_name,
            "input_trajectory_filepaths": [trajectory_name],
        }
        return metadata
