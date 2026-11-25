from http import HTTPStatus
from typing import Annotated

from core.config import API_PREFIX
from core.responses import problems
from fastapi import APIRouter, Query

from modules.experiments.dependencies import ExperimentDep
from modules.setup.schemas import DEFAULT_SETUP_NOTEBOOK, SetupRun, StartSetupRequest
from modules.setup.service import SetupService, SetupServiceDep

router = APIRouter(prefix=f"{API_PREFIX}/experiments", tags=["Setup"])

NotebookQuery = Annotated[str, Query(min_length=1, description="Experiment-relative notebook")]


@router.post(
    "/{experiment_id}/setup",
    status_code=HTTPStatus.ACCEPTED,
    summary="Run setup",
    description="Execute the setup notebook headless in a Kubernetes Job.",
    operation_id="startSetup",
    response_description="Setup run accepted",
    responses=problems(400, 403, 404, 409),
)
async def start_setup(experiment: ExperimentDep, service: SetupServiceDep, body: StartSetupRequest) -> SetupRun:
    """Start a setup run."""
    notebook = SetupService.resolve_notebook(experiment, body.notebook)
    return await service.start(experiment, notebook, body.tier, body.gpu)


@router.get(
    "/{experiment_id}/setup",
    summary="Get the setup run",
    operation_id="getSetup",
    response_description="Setup run",
    responses=problems(400, 404),
)
async def get_setup(
    experiment: ExperimentDep, service: SetupServiceDep, notebook: NotebookQuery = DEFAULT_SETUP_NOTEBOOK
) -> SetupRun:
    """Get the notebook's setup run (404 when setup never ran)."""
    return await service.get(experiment, SetupService.resolve_notebook(experiment, notebook))


@router.delete(
    "/{experiment_id}/setup",
    status_code=HTTPStatus.NO_CONTENT,
    summary="Stop the setup run",
    operation_id="stopSetup",
    responses=problems(400, 404),
)
async def stop_setup(
    experiment: ExperimentDep, service: SetupServiceDep, notebook: NotebookQuery = DEFAULT_SETUP_NOTEBOOK
) -> None:
    """Stop the run in progress."""
    await service.stop(experiment, SetupService.resolve_notebook(experiment, notebook))
