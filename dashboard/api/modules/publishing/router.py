from http import HTTPStatus
from typing import cast

from core.config import API_PREFIX
from core.responses import problems
from fastapi import APIRouter
from fastapi.responses import JSONResponse

from modules.experiments.dependencies import ExperimentDep
from modules.mdrepo.dependencies import TokensDep
from modules.publishing.schemas import MDPositPublication, MDRepoPublication, PublishRequest, PublishStatus
from modules.publishing.service import PublishingServiceDep

router = APIRouter(prefix=f"{API_PREFIX}/experiments", tags=["Experiments"])


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
    experiment: ExperimentDep,
    service: PublishingServiceDep,
    tokens: TokensDep,
    body: PublishRequest | None = None,
) -> JSONResponse:
    """Publish experiment to the requested target."""
    body = body or PublishRequest()
    if body.target == "invenio":
        return JSONResponse(await service.publish_mdrepo(experiment, tokens), status_code=HTTPStatus.ACCEPTED)
    return JSONResponse(await service.publish_mdposit(experiment, body.simulation_path), status_code=HTTPStatus.CREATED)


@router.get(
    "/{experiment_id}/publish/status",
    summary="Get MDRepo upload status",
    operation_id="getPublishStatus",
    response_description="Publication status",
    responses=problems(404),
)
async def publish_status(experiment: ExperimentDep, service: PublishingServiceDep) -> PublishStatus:
    """Durable MDRepo upload status: the PVC state document merged with live Kubernetes Job state."""
    return cast("PublishStatus", await service.status(experiment))
