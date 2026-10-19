from http import HTTPStatus

from core.config import API_PREFIX
from core.dependencies import SessionDep, dump
from core.errors import NotFound
from core.responses import problems
from fastapi import APIRouter, Response

from modules.experiments.dependencies import ExperimentDep
from modules.models import Experiment, Notebook
from modules.notebooks.schemas import Notebook as NotebookOut
from modules.notebooks.schemas import StartNotebookRequest

router = APIRouter(prefix=f"{API_PREFIX}/experiments/{{experiment_id}}/notebook", tags=["Notebooks"])


def _notebook(experiment: Experiment) -> Notebook:
    if experiment.notebook is None:
        raise NotFound(f"Experiment {experiment.id} has no notebook")
    return experiment.notebook


@router.get(
    "",
    summary="Get an experiment notebook",
    operation_id="getNotebook",
    response_description="Notebook",
    responses=problems(404),
)
async def get_notebook(session: SessionDep, experiment: ExperimentDep) -> NotebookOut:
    """Get the notebook instance of an experiment."""
    notebook = _notebook(experiment)
    await notebook.refresh()
    return await dump(session, NotebookOut, notebook)


@router.post(
    "",
    status_code=HTTPStatus.CREATED,
    summary="Start an experiment notebook",
    operation_id="startNotebook",
    response_description="Started notebook",
    responses=problems(400, 403, 404),
)
async def start_notebook(
    session: SessionDep, experiment: ExperimentDep, body: StartNotebookRequest | None = None
) -> NotebookOut:
    """Start the notebook pod of an experiment (optional `tier` and `gpu`)."""
    body = body or StartNotebookRequest()
    notebook = _notebook(experiment)
    await notebook.start(tier=body.tier, gpu=body.gpu)
    await session.commit()
    return await dump(session, NotebookOut, notebook)


@router.delete(
    "",
    status_code=HTTPStatus.NO_CONTENT,
    response_class=Response,
    summary="Stop an experiment notebook",
    operation_id="stopNotebook",
    response_description="Operation completed successfully",
    responses=problems(404),
)
async def stop_notebook(experiment: ExperimentDep) -> None:
    """Stop the notebook pod of an experiment."""
    await _notebook(experiment).stop()
