from http import HTTPStatus
from typing import Annotated, Literal

from core.config import API_PREFIX
from core.dependencies import SessionDep, dump, dump_many
from core.enums import Engine
from core.errors import BadRequest
from core.responses import problems
from fastapi import APIRouter, File, Form, Response, UploadFile
from fastapi.responses import JSONResponse

from modules.experiments.dependencies import ExperimentDep, ReadyExperimentDep
from modules.experiments.schemas import Experiment as ExperimentOut
from modules.experiments.schemas import UpdateExperiment
from modules.experiments.service import ExperimentServiceDep
from modules.mdrepo.dependencies import TokensDep
from modules.population.schemas import PopulationJob

router = APIRouter(prefix=f"{API_PREFIX}/experiments", tags=["Experiments"])


@router.get(
    "",
    summary="List experiments",
    operation_id="listExperiments",
    response_description="Experiments",
    responses=problems(),
)
async def list_all(session: SessionDep, service: ExperimentServiceDep, tokens: TokensDep) -> list[ExperimentOut]:
    """
    List all experiments.

    The dashboard polls this every 5s while any job is live; remote state of
    all experiments is fetched concurrently.
    """
    return await dump_many(session, ExperimentOut, await service.list_experiments(tokens))


@router.post(
    "",
    status_code=HTTPStatus.CREATED,
    summary="Create an experiment",
    operation_id="createExperiment",
    response_model=ExperimentOut,
    response_description="Created experiment",
    responses={
        HTTPStatus.ACCEPTED.value: {"model": PopulationJob, "description": "Datahugger population queued"},
        **problems(400),
    },
)
async def create(
    session: SessionDep,
    service: ExperimentServiceDep,
    tokens: TokensDep,
    experiment_name: Annotated[str, Form(alias="experiment-name", min_length=1)],
    source_type: Annotated[Literal["pdb", "repo", "file", "datahugger"], Form(alias="type")],
    simulation_files: Annotated[list[UploadFile], File(alias="simulation-files", default_factory=list)],
    pdb: Annotated[str | None, Form()] = None,
    repo_url: Annotated[str | None, Form(alias="repo-url")] = None,
    notebooks_repo: Annotated[str | None, Form(alias="notebooks-repo")] = None,
    access_token: Annotated[str | None, Form(alias="access-token")] = None,
    notebook_module_id: Annotated[str | None, Form(alias="notebook-module")] = None,
    engine: Annotated[Engine, Form()] = Engine.GMX,
) -> Response:
    """
    Create a new experiment from PDB, repository URL, uploaded files, or Datahugger-NG.

    Datahugger-NG creation is asynchronous: it prepares the notebooks, commits a
    provisional experiment, queues a one-shot download worker, and returns the
    operation identifiers while the import progresses in the background.
    """
    if source_type == "datahugger":
        if not repo_url:
            raise BadRequest("Invalid experiment type or missing data.")
        operation = await service.create_population(
            experiment_name,
            repo_url,
            notebooks_repo=notebooks_repo,
            access_token=access_token,
            notebook_module_id=notebook_module_id,
            engine=engine,
        )
        payload = PopulationJob(operation_id=operation.id, experiment_id=operation.experiment_id)
        return JSONResponse(status_code=HTTPStatus.ACCEPTED, content=payload.model_dump(mode="json"))

    experiment = await service.create(
        experiment_name,
        source_type,
        pdb=pdb,
        repo_url=repo_url,
        files=simulation_files,
        notebooks_repo=notebooks_repo,
        access_token=access_token,
        notebook_module_id=notebook_module_id,
        engine=engine,
    )
    await service.refresh_all([experiment], tokens)
    data = await dump(session, ExperimentOut, experiment)
    return JSONResponse(status_code=HTTPStatus.CREATED, content=data.model_dump(mode="json"))


@router.get(
    "/{experiment_id}",
    summary="Get an experiment",
    operation_id="getExperiment",
    response_description="Experiment",
    responses=problems(404),
)
async def get(
    session: SessionDep, experiment: ExperimentDep, service: ExperimentServiceDep, tokens: TokensDep
) -> ExperimentOut:
    """Get an experiment by ID."""
    await service.refresh_all([experiment], tokens)
    return await dump(session, ExperimentOut, experiment)


@router.post(
    "/{experiment_id}/population/cancel",
    summary="Cancel a Datahugger population",
    operation_id="cancelExperimentPopulation",
    response_description="Cancelled experiment",
    responses=problems(404, 409),
)
async def cancel_population(
    session: SessionDep, experiment: ExperimentDep, service: ExperimentServiceDep, tokens: TokensDep
) -> ExperimentOut:
    """Stop an active Datahugger import after its worker is confirmed deleted."""
    await service.population.cancel(experiment)
    await service.refresh_all([experiment], tokens)
    return await dump(session, ExperimentOut, experiment)


@router.patch(
    "/{experiment_id}",
    summary="Update an experiment",
    operation_id="updateExperiment",
    response_description="Updated experiment",
    responses=problems(400, 404, 409),
)
async def update(
    session: SessionDep,
    experiment: ReadyExperimentDep,
    service: ExperimentServiceDep,
    tokens: TokensDep,
    body: UpdateExperiment,
) -> ExperimentOut:
    """Update experiment properties (currently only the name)."""
    await service.rename(experiment, body.name)
    await service.refresh_all([experiment], tokens)
    return await dump(session, ExperimentOut, experiment)


@router.delete(
    "/{experiment_id}",
    status_code=HTTPStatus.NO_CONTENT,
    response_class=Response,
    summary="Delete an experiment",
    operation_id="deleteExperiment",
    response_description="Operation completed successfully",
    responses=problems(404, 409),
)
async def delete(experiment: ExperimentDep, service: ExperimentServiceDep) -> None:
    """Delete an experiment and all associated resources."""
    await service.delete(experiment)
