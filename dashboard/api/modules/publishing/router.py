from http import HTTPStatus

from core.config import API_PREFIX
from core.dependencies import SessionDep
from core.errors import BadRequest, Conflict, Unauthorized
from core.responses import problems
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from pydantic import TypeAdapter

from modules.experiments.dependencies import ExperimentDep
from modules.mdrepo.tokens import MDRepoTokenManager
from modules.publishing.schemas import MDPositPublication, MDRepoPublication, PublishRequest, PublishStatus

router = APIRouter(prefix=f"{API_PREFIX}/experiments", tags=["Experiments"])

_publish_status = TypeAdapter(PublishStatus)


@router.post(
    "/{experiment_id}/publish",
    summary="Publish an experiment",
    operation_id="publishExperiment",
    response_model=None,
    responses={
        201: {"model": MDPositPublication, "description": "MDPosit publication package"},
        202: {"model": MDRepoPublication, "description": "MDRepo publication accepted"},
        **problems(400, 401, 404),
    },
)
async def publish(
    request: Request, session: SessionDep, experiment: ExperimentDep, body: PublishRequest | None = None
) -> JSONResponse:
    """
    Publish experiment to the requested target.

    Raises:
        BadRequest: If MDPosit publishing lacks a simulation_path.
        Unauthorized: If the user is not authenticated with MDRepo for Invenio publishing.
        Conflict: If there is nothing publishable yet.
    """
    body = body or PublishRequest()

    if body.target == "invenio":
        credentials = await MDRepoTokenManager(request.session).get_credentials()
        if credentials is None:
            raise Unauthorized("Not authenticated with MDRepo. Please authenticate first.")

        # Same gate as the wizard's can_publish unlock. A stale URL/bookmark
        # must not create an MDRepo draft for an experiment with nothing publishable.
        await experiment.refresh_jobs()
        if not experiment.can_publish:
            raise Conflict("Nothing to publish yet: no finished or stopped run and no existing publication.")

        # TODO: Add endpoint to fetch available communities from MDRepo and allow user to select from a dropdown in the publish UI.
        #       Pass the selected community to this endpoint and use it when publishing the experiment instead of hardcoding 'ceitec'.
        result = await experiment.publish(session, target="invenio", community="ceitec", credentials=credentials)
        await session.commit()
        return JSONResponse(result, status_code=HTTPStatus.ACCEPTED)

    if not body.simulation_path:
        raise BadRequest("MDPosit publish requires simulation_path.")
    result = await experiment.publish(session, target="mdposit", simulation_path=body.simulation_path)
    await session.commit()
    return JSONResponse(result, status_code=HTTPStatus.CREATED)


@router.get(
    "/{experiment_id}/publish/status",
    summary="Get MDRepo upload status",
    operation_id="getPublishStatus",
    response_description="Publication status",
    responses=problems(404),
)
async def publish_status(experiment: ExperimentDep) -> PublishStatus:
    """Durable MDRepo upload status: the PVC state document merged with live Kubernetes Job state."""
    return _publish_status.validate_python(await experiment.get_publish_status())
