"""Experiments: creation from a structure source, remote-state refresh, and teardown."""

import asyncio
import logging
import threading
from collections.abc import Awaitable, Callable, Sequence
from http import HTTPStatus
from shutil import rmtree
from typing import Annotated, Literal
from urllib.parse import urlparse

import anyio
from clients import mdposit
from core.concurrency import gather
from core.config import DATA_DIR, DEFAULT_NOTEBOOKS_REPO
from core.dependencies import ClientsDep, SessionDep
from core.enums import Engine, SourceType
from core.errors import ApiError, BadRequest, Conflict, NotFound
from core.utils import get_unique_id, secure_filename
from core.validators import validate_git_url, validate_http_url
from fastapi import Depends, UploadFile
from sqlalchemy import select

from modules.archive.service import ArchiveService
from modules.experiments.models import Experiment
from modules.experiments.sources import (
    fetch_pdb,
    import_invenio_repo,
    import_mdposit_repo,
    resolve_repo_link,
    validate_pdb_content,
)
from modules.jobs.service import JobsService
from modules.mdrepo.tokens import MDRepoTokenManager
from modules.notebooks.catalog import NotebookModule, load_catalog
from modules.notebooks.models import Notebook
from modules.notebooks.service import NotebookService
from modules.publishing.service import PublishingService, needs_mdrepo_sync
from modules.publishing.status import UploadState

logger = logging.getLogger(__name__)

_UPLOAD_CHUNK_BYTES = 1024 * 1024

type _Populate = Callable[[str], Awaitable[dict]]


class ExperimentService:
    """Experiments with every remote state their serialization reads."""

    def __init__(self, session: SessionDep, clients: ClientsDep) -> None:
        """Bind to the request session, the upstream clients, and the feature services."""
        self._session = session
        self._clients = clients
        self.jobs = JobsService(session, clients)
        self.notebooks = NotebookService(clients)
        self.publishing = PublishingService(session, clients)
        self.archive = ArchiveService(session, clients)

    # --- reads ----------------------------------------------------------------------

    async def list_experiments(self, tokens: MDRepoTokenManager) -> Sequence[Experiment]:
        """
        All experiments, refreshed concurrently (relationships load eagerly).

        The dashboard polls this every 5s while any job is live.
        """
        experiments = (await self._session.execute(select(Experiment))).scalars().all()
        await self.refresh_all(experiments, tokens)
        return experiments

    async def refresh_all(self, experiments: Sequence[Experiment], tokens: MDRepoTokenManager) -> None:
        """Fetch the remote state of `experiments` (no DB I/O; the caller commits)."""
        token = await self._mdrepo_token(experiments, tokens)
        await gather(*(self.refresh(experiment, token) for experiment in experiments))

    async def refresh(self, experiment: Experiment, mdrepo_token: str | None = None) -> None:
        """Fetch every remote state the experiment's serialization reads (no DB I/O; the caller commits)."""
        await gather(
            self.notebooks.refresh(experiment.notebook) if experiment.notebook is not None else asyncio.sleep(0),
            self.jobs.refresh(experiment),
            self.publishing.sync_mdrepo_status(experiment, mdrepo_token),
            self.archive.refresh_state(experiment),
        )

    @staticmethod
    async def _mdrepo_token(experiments: Sequence[Experiment], tokens: MDRepoTokenManager) -> str | None:
        """Session MDRepo token, fetched only when an experiment's MDRepo state is due for a sync."""
        if tokens.has_session() and any(needs_mdrepo_sync(experiment) for experiment in experiments):
            return await tokens.get_valid_token()
        return None

    # --- creation -------------------------------------------------------------------

    async def create(
        self,
        name: str,
        source_type: Literal["pdb", "repo", "file"],
        *,
        pdb: str | None = None,
        repo_url: str | None = None,
        files: list[UploadFile] | None = None,
        notebooks_repo: str | None = None,
        access_token: str | None = None,
        notebook_module_id: str | None = None,
        engine: Engine = Engine.GMX,
    ) -> Experiment:
        """
        Create an experiment from a PDB source, a repository URL, or uploaded files.

        Raises:
            BadRequest: If the notebook module, repository, or source data is invalid.
        """
        repo = notebooks_repo if notebooks_repo is not None else DEFAULT_NOTEBOOKS_REPO
        module = None
        if notebook_module_id:
            # Curated mode: server resolves module and repository; no client URL trusted.
            module = load_catalog().get(notebook_module_id, engine.value)
            if module is None:
                raise BadRequest(f"Unknown or incompatible notebook module: {notebook_module_id}")
            repo = module.repository or DEFAULT_NOTEBOOKS_REPO
            if module.repository is not None:
                # Guard against unsafe schemes even on trusted catalog URLs.
                validate_git_url(module.repository)
            # Never forward a client token to a curated (server-trusted) repository.
            access_token = None
        else:
            validate_git_url(repo)

        match source_type:
            case "pdb" if pdb:
                return await self.from_pdb(name, pdb, repo, access_token, engine=engine, notebook_module=module)
            case "repo" if repo_url:
                return await self.from_repo(name, repo_url, repo, access_token, engine=engine, notebook_module=module)
            case "file" if files:
                return await self.from_files(name, files, repo, access_token, engine=engine, notebook_module=module)
            case _:
                raise BadRequest("Invalid experiment type or missing data.")

    async def prepare_env(
        self, notebooks_repo: str, access_token: str | None = None, notebook_module: NotebookModule | None = None
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
        await anyio.Path(experiment_dir).mkdir(parents=True, exist_ok=True)
        git = self._clients.git
        try:
            if notebook_module is not None and not notebook_module.is_root:
                await git.clone_module(notebooks_repo, notebook_module.path, experiment_dir, access_token)
            else:
                await git.clone(notebooks_repo, experiment_dir, access_token)
        except BaseException:
            await anyio.to_thread.run_sync(lambda: rmtree(experiment_dir, ignore_errors=True))
            raise

        return experiment_id

    async def _create(self, experiment_id: str, populate: _Populate, **columns: object) -> Experiment:
        """Populate the prepared directory, then persist the experiment with its notebook; clean up on failure."""
        try:
            columns.update(await populate(experiment_id))
            # Empty collections up front: the new row must never lazy-load them later.
            experiment = Experiment(
                id=experiment_id,
                notebook=Notebook(experiment_id=experiment_id),
                tuner_jobs=[],
                simulation_jobs=[],
                analysis_jobs=[],
                **columns,
            )
            self._session.add(experiment)
            await self._session.commit()
        except BaseException:
            await anyio.to_thread.run_sync(lambda: rmtree(DATA_DIR / experiment_id, ignore_errors=True))
            await self._session.rollback()
            raise

        logger.info(f"Created experiment {experiment.id}")
        return experiment

    @staticmethod
    def _module_columns(engine: Engine, notebooks_repo: str, notebook_module: NotebookModule | None) -> dict:
        return {
            "notebooks_repo": notebooks_repo,
            "engine": engine,
            "module_name": notebook_module.name if notebook_module else None,
            "module_category": notebook_module.category if notebook_module else None,
        }

    async def from_pdb(
        self,
        name: str,
        pdb_source: str,
        notebooks_repo: str,
        access_token: str | None = None,
        engine: Engine = Engine.GMX,
        notebook_module: NotebookModule | None = None,
    ) -> Experiment:
        """
        Create experiment from a PDB ID or a direct URL to a PDB file (404 when the source is not found).

        A value without a URL scheme (e.g. ``1A2B``) is treated as an RCSB PDB ID
        and downloaded from ``files.rcsb.org``. A value with a URL scheme is fetched
        as-is; only ``http`` and ``https`` schemes are accepted.
        """
        experiment_id = await self.prepare_env(notebooks_repo, access_token, notebook_module)
        source = pdb_source.strip()

        async def populate(exp_id: str) -> dict:
            if urlparse(source).scheme:
                url = validate_http_url(source)
                source_ref = url
            else:
                source_ref = source.upper()
                url = f"https://files.rcsb.org/download/{source_ref}.pdb"

            response = await fetch_pdb(self._clients.http, url)
            if response.status_code == HTTPStatus.NOT_FOUND:
                raise NotFound(f"PDB source '{source}' not found.")
            if response.status_code != HTTPStatus.OK:
                raise ApiError(
                    HTTPStatus.INTERNAL_SERVER_ERROR,
                    "Failed to download PDB file.",
                    "urn:mddash:upstream-download-failed",
                    "The structure source couldn't be fetched; try again, or use a different PDB ID / file.",
                )
            validate_pdb_content(response.content)
            await anyio.Path(DATA_DIR / exp_id / "input.pdb").write_bytes(response.content)
            return {"source_type": SourceType.PDB, "source_ref": source_ref}

        return await self._create(
            experiment_id, populate, name=name, **self._module_columns(engine, notebooks_repo, notebook_module)
        )

    async def from_repo(
        self,
        name: str,
        repo_link: str,
        notebooks_repo: str,
        access_token: str | None = None,
        engine: Engine = Engine.GMX,
        notebook_module: NotebookModule | None = None,
    ) -> Experiment:
        """Create experiment from a supported repository URL (InvenioRDM or MDPosit, DOIs resolved)."""
        experiment_id = await self.prepare_env(notebooks_repo, access_token, notebook_module)

        async def populate(exp_id: str) -> dict:
            resolved_repo_link = await resolve_repo_link(self._clients.http, repo_link)
            if mdposit.is_mdposit_url(resolved_repo_link):
                await import_mdposit_repo(self._clients.mdposit, resolved_repo_link, exp_id)
            else:
                await import_invenio_repo(self._clients.http, resolved_repo_link, exp_id)
            return {"source_type": SourceType.REPO, "source_ref": resolved_repo_link}

        return await self._create(
            experiment_id, populate, name=name, **self._module_columns(engine, notebooks_repo, notebook_module)
        )

    async def from_files(
        self,
        name: str,
        files: list[UploadFile],
        notebooks_repo: str,
        access_token: str | None = None,
        engine: Engine = Engine.GMX,
        notebook_module: NotebookModule | None = None,
    ) -> Experiment:
        """
        Create experiment from file uploads.

        Raises:
            BadRequest: If no files are provided.
        """
        if not files:
            raise BadRequest("No files provided")

        experiment_id = await self.prepare_env(notebooks_repo, access_token, notebook_module)

        async def populate(exp_id: str) -> dict:
            filenames = []
            for file in files:
                if not file.filename:
                    continue
                filename = secure_filename(file.filename)
                async with await anyio.open_file(DATA_DIR / exp_id / filename, "wb") as out:
                    while chunk := await file.read(_UPLOAD_CHUNK_BYTES):
                        await out.write(chunk)
                filenames.append(filename)
            return {"source_type": SourceType.FILE, "source_files": filenames}

        return await self._create(
            experiment_id, populate, name=name, **self._module_columns(engine, notebooks_repo, notebook_module)
        )

    # --- changes --------------------------------------------------------------------

    async def rename(self, experiment: Experiment, name: str) -> None:
        """Rename an experiment."""
        experiment.name = name
        await self._session.commit()

    async def delete(self, experiment: Experiment) -> None:
        """
        Delete an experiment with all its resources.

        Raises:
            Conflict: If an MDRepo upload is queued or running.
        """
        # Reject deletion while an upload is active (check PVC + live Job).
        if await self.publishing.upload_state(experiment.id) in UploadState.active():
            raise Conflict(
                "Cannot delete experiment during active MDRepo upload. Wait for completion or retry after failure."
            )
        # Delete wins over in-flight archive/restore work; the archive prefix is purged after.
        await self.archive.delete_jobs(experiment.id)
        needs_purge = experiment.archived_at is not None or experiment.archived_step is not None

        await self.notebooks.stop_if_running(experiment.notebook)

        # Analysis K8s Jobs have no TTL: rows cascading away without this would orphan them.
        for job in self.jobs.all_jobs(experiment):
            try:
                await self.jobs.delete_remote(job)
            except Exception:
                logger.exception(f"Failed to delete {type(job).__name__} {job.id}")

        experiment_dir = DATA_DIR / experiment.id

        def del_dir() -> None:
            rmtree(experiment_dir, ignore_errors=True)
            logger.info(f"Deleted experiment directory: {experiment_dir}")

        # The response must not wait for a large tree to be removed.
        threading.Thread(target=del_dir, daemon=True).start()

        if needs_purge:
            await self.archive.purge(experiment.id)

        await self._session.delete(experiment)
        await self._session.commit()


ExperimentServiceDep = Annotated[ExperimentService, Depends()]
