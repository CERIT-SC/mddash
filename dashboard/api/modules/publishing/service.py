"""Publication: MDRepo drafts with durable upload Jobs, MDPosit packages, and MDRepo status mirroring."""

import logging
from http import HTTPStatus
from typing import Annotated

import anyio
import httpx
from core.cache import mdrepo_status_cache
from core.config import (
    DATA_DIR,
    MDREPO_API_URL,
    MDREPO_CLIENT_ID,
    MDREPO_CLIENT_SECRET,
    MDREPO_RECORD_NAME,
    MDREPO_TOKEN_URL,
)
from core.dependencies import ClientsDep, SessionDep
from core.enums import Engine
from core.errors import ApiError, BadRequest, Conflict, Unauthorized
from fastapi import Depends

from modules.archive.service import ArchiveService
from modules.experiments.models import Experiment
from modules.experiments.sources import list_simulations
from modules.jobs.service import JobsService
from modules.mdrepo.tokens import MDRepoCredentials, MDRepoTokenManager
from modules.publishing import mdposit
from modules.publishing.status import REASON_JOB_MISSING, UploadState, read_status
from modules.publishing.submission import (
    SubmissionError,
    delete_upload_resources,
    read_upload_state,
    submit_upload_job,
)

logger = logging.getLogger(__name__)

# TODO: Add an endpoint listing MDRepo communities and let the publish UI pick one instead of hardcoding 'ceitec'.
DEFAULT_COMMUNITY = "ceitec"


def needs_mdrepo_sync(experiment: Experiment) -> bool:
    """Whether `sync_mdrepo_status` would contact MDRepo (a draft/record exists and is not cached)."""
    return bool(experiment.mdrepo_id) and experiment.mdrepo_id not in mdrepo_status_cache


def _mdrepo_unavailable(description: str = "Failed to create experiment in MDRepo.") -> ApiError:
    return ApiError(
        HTTPStatus.INTERNAL_SERVER_ERROR,
        description,
        "urn:mddash:upstream-unavailable",
        "MDRepo didn't respond as expected; try again in a moment.",
    )


class PublishingService:
    """Publishing experiments to MDRepo (draft + upload Job) or MDPosit (VRE Lite package)."""

    def __init__(self, session: SessionDep, clients: ClientsDep) -> None:
        """Bind to the request session, the publication upstreams, and the job/archive services."""
        self._session = session
        self._k8s = clients.k8s
        self._mdrepo = clients.mdrepo
        self._metadump = clients.metadump
        self._jobs = JobsService(session, clients)
        self._archive = ArchiveService(session, clients)

    async def sync_mdrepo_status(self, experiment: Experiment, access_token: str | None) -> None:
        """Check whether the MDRepo record still exists and mirror its published flag (cached per record)."""
        record_id = experiment.mdrepo_id
        if not access_token or not record_id or record_id in mdrepo_status_cache:
            return
        mdrepo_status_cache[record_id] = True
        try:
            status = await self._mdrepo.check_experiment_status(access_token, record_id)
        except Exception:
            logger.exception(f"Failed to check MDRepo status for experiment '{record_id}'")
            return
        if status is None:
            experiment.mdrepo_id = None
            experiment.mdrepo_published = None
        else:
            experiment.mdrepo_published = status

    async def upload_state(self, experiment_id: str) -> str | None:
        """Upload state reconciled from the PVC status file and the live Job."""
        return await read_upload_state(self._k8s, experiment_id, DATA_DIR)

    async def _require_not_archived(self, experiment: Experiment) -> None:
        if await self._archive.refresh_state(experiment) is not None:
            raise Conflict(
                "Experiment is archived or an archive/restore is in flight. "
                "Publishing reads the local files; restore the experiment (or wait) first."
            )

    async def publish_mdrepo(self, experiment: Experiment, tokens: MDRepoTokenManager) -> dict:
        """
        Publish to MDRepo as a draft and start a durable upload Job (idempotent: returns the active upload).

        Raises:
            Unauthorized: If the user is not authenticated with MDRepo.
            Conflict: If there is nothing publishable yet, the experiment is archived, or it is already published.
        """
        credentials = await tokens.get_credentials()
        if credentials is None:
            raise Unauthorized("Not authenticated with MDRepo. Please authenticate first.")

        # Same gate as the wizard's can_publish unlock. A stale URL/bookmark
        # must not create an MDRepo draft for an experiment with nothing publishable.
        await self._jobs.refresh(experiment)
        if not experiment.can_publish:
            raise Conflict("Nothing to publish yet: no finished or stopped run and no existing publication.")

        return await self.publish_invenio(experiment, credentials)

    async def publish_invenio(
        self, experiment: Experiment, credentials: MDRepoCredentials, community: str = DEFAULT_COMMUNITY
    ) -> dict:
        """Publish to MDRepo as a draft and start a durable upload Job (409 while archived)."""
        await self._require_not_archived(experiment)
        result = await self._publish_invenio(experiment, community, credentials)
        await self._session.commit()
        return result

    async def publish_mdposit(self, experiment: Experiment, simulation_path: str | None) -> dict:
        """
        Prepare the MDPosit publication package of one simulation (409 while archived).

        Raises:
            BadRequest: If no simulation_path is given.
        """
        if not simulation_path:
            raise BadRequest("MDPosit publish requires simulation_path.")
        await self._require_not_archived(experiment)
        result = await anyio.to_thread.run_sync(mdposit.prepare_package, experiment, simulation_path)
        await self._session.commit()
        return result

    async def _publish_invenio(self, experiment: Experiment, community: str, credentials: MDRepoCredentials) -> dict:
        access_token = credentials.access_token

        # A published record cannot be retried as a draft upload.
        if experiment.mdrepo_published is True:
            raise Conflict("Experiment is already published. Cannot retry as draft upload.")

        upload_state = await self.upload_state(experiment.id)

        # Skip retry only when a completed upload still has a live draft.
        if upload_state == UploadState.COMPLETED.value and experiment.mdrepo_id:
            raise Conflict("Upload already completed. Use MDRepo to view or edit the published record.")

        # If an upload is already active, return it (idempotent retry).
        if upload_state in UploadState.active():
            status = await anyio.to_thread.run_sync(read_status, experiment.id, DATA_DIR)
            return {
                "id": experiment.mdrepo_id or "",
                "links": {},
                "upload_id": status.attempt_id if status else "",
                "upload_state": upload_state,
                "draft_url": experiment.mdrepo_record_url,
            }

        # If a previous attempt failed, clean up its K8s resources before retrying.
        if upload_state == UploadState.FAILED.value:
            await delete_upload_resources(self._k8s, experiment.id)

        # Reuse the draft only if it still exists. The user may have deleted it in MDRepo.
        if (
            experiment.mdrepo_id
            and await self._mdrepo.check_experiment_status(access_token, experiment.mdrepo_id) is not None
        ):
            mdrepo_id = experiment.mdrepo_id
            mdrepo_experiment: dict = {"id": mdrepo_id, "links": {}}
        else:
            experiment.mdrepo_id = None
            experiment.mdrepo_published = None
            mdrepo_experiment = await self._create_draft(experiment, access_token, community)
            mdrepo_id = experiment.mdrepo_id or ""

        if not mdrepo_id:
            raise _mdrepo_unavailable()

        # Submit the upload Job: writes queued status, creates Secret+Job, waits for admission.
        try:
            attempt_id = await submit_upload_job(
                self._k8s,
                experiment_id=experiment.id,
                mdrepo_id=mdrepo_id,
                credential_data={
                    "access_token": access_token,
                    "refresh_token": credentials.refresh_token,
                    "expires_at": credentials.expires_at,
                    "client_id": MDREPO_CLIENT_ID,
                    "client_secret": MDREPO_CLIENT_SECRET,
                    "api_url": MDREPO_API_URL,
                    "record_name": MDREPO_RECORD_NAME,
                    "token_url": MDREPO_TOKEN_URL,
                },
                data_dir=DATA_DIR,
            )
        except SubmissionError as e:
            logger.error("Upload Job submission failed for experiment %s: %s", experiment.id, e)
            raise _mdrepo_unavailable("The MDRepo upload could not be started.") from e

        logger.info("Durable upload Job submitted for experiment %s (attempt %s)", experiment.id, attempt_id)
        return {
            "id": mdrepo_id,
            "links": mdrepo_experiment.get("links", {}),
            "upload_id": attempt_id,
            "upload_state": UploadState.QUEUED.value,
            "draft_url": experiment.mdrepo_record_url,
        }

    async def _create_draft(self, experiment: Experiment, access_token: str, community: str) -> dict:
        """Create a new Invenio draft and persist its ID."""
        gmx_simulations = [s for s in list_simulations(experiment) if s.engine == Engine.GMX.value and s.valid]
        tpr_paths = [
            DATA_DIR / experiment.id / topology
            for sim in gmx_simulations
            if (topology := sim.resolved_files.get("topology"))
        ]
        simulations = await self._metadump.extract_metadata_bulk(tpr_paths) if tpr_paths else []

        try:
            mdrepo_experiment = await self._mdrepo.create_experiment(
                access_token, community, {"simulations": simulations}
            )
        except (ValueError, httpx.HTTPError) as e:
            logger.error("MDRepo draft creation failed for experiment %s: %s", experiment.id, e)
            raise _mdrepo_unavailable() from e
        mdrepo_id = mdrepo_experiment.get("id")
        if mdrepo_id is None:
            raise _mdrepo_unavailable()

        experiment.mdrepo_id = mdrepo_id
        experiment.mdrepo_published = False
        await self._session.commit()

        logger.info("Created MDRepo experiment with ID '%s' for experiment '%s'", mdrepo_id, experiment.id)
        return mdrepo_experiment

    async def status(self, experiment: Experiment) -> dict:
        """Return the durable MDRepo upload status, merging the PVC document with live Job state."""
        status = await anyio.to_thread.run_sync(read_status, experiment.id, DATA_DIR)
        effective_state = await self.upload_state(experiment.id)

        result: dict = {
            "experiment_id": experiment.id,
            "mdrepo_id": experiment.mdrepo_id,
            "draft_url": experiment.mdrepo_record_url,
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
            # A missing Job overrides the file's active state (job_missing).
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


PublishingServiceDep = Annotated[PublishingService, Depends()]
