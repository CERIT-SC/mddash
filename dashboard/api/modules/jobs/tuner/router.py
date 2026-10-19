from http import HTTPStatus
from typing import Annotated

from core.config import API_PREFIX
from core.dependencies import ExperimentIdPath, SessionDep, dump, dump_many
from core.responses import problems
from fastapi import APIRouter, Path, Response

from modules.jobs.tuner.schemas import TunerJob as TunerJobOut
from modules.jobs.tuner.schemas import TunerJobRequest
from modules.jobs.tuner.service import TunerServiceDep

router = APIRouter(prefix=f"{API_PREFIX}/experiments/{{experiment_id}}/tuner", tags=["Tuner"])

SimulationPath = Annotated[str, Path(min_length=1)]
TrialId = Annotated[str, Path(min_length=1)]


@router.get(
    "", summary="List tuner jobs", operation_id="listTunerJobs", response_description="Tuner jobs", responses=problems()
)
async def list_jobs(
    session: SessionDep, service: TunerServiceDep, experiment_id: ExperimentIdPath
) -> list[TunerJobOut]:
    """List all tuner jobs of an experiment."""
    return await dump_many(session, TunerJobOut, await service.list_jobs(experiment_id))


@router.post(
    "",
    status_code=HTTPStatus.CREATED,
    summary="Start a tuner job",
    operation_id="startTunerJob",
    response_description="Started tuner job",
    responses={200: {"model": TunerJobOut, "description": "Existing tuner job"}, **problems(400, 404)},
)
async def start_job(
    session: SessionDep,
    service: TunerServiceDep,
    response: Response,
    experiment_id: ExperimentIdPath,
    body: TunerJobRequest,
) -> TunerJobOut:
    """Start a tuner job for a simulation manifest; an existing healthy job is returned instead (200)."""
    job, created = await service.start(experiment_id, body.simulation_path, body.nsteps)
    if not created:
        response.status_code = HTTPStatus.OK
    return await dump(session, TunerJobOut, job)


@router.post(
    "/{simulation_path:path}/stop",
    status_code=HTTPStatus.NO_CONTENT,
    response_class=Response,
    summary="Stop a tuner job",
    operation_id="stopTunerJob",
    response_description="Operation completed successfully",
    responses=problems(404),
)
async def stop_job(service: TunerServiceDep, experiment_id: ExperimentIdPath, simulation_path: SimulationPath) -> None:
    """Stop a running tuner job, keeping its observed trials."""
    await service.stop_by_path(experiment_id, simulation_path)


@router.get(
    "/{simulation_path:path}/trials/{trial_id}/stdout",
    summary="Get tuner trial standard output",
    operation_id="getTunerTrialStdout",
    response_description="Text represented as a JSON string",
    responses=problems(404),
)
async def get_trial_stdout(
    service: TunerServiceDep, experiment_id: ExperimentIdPath, simulation_path: SimulationPath, trial_id: TrialId
) -> str:
    """Stdout log of a tuning trial."""
    return await service.trial_log(experiment_id, simulation_path, trial_id, "stdout")


@router.get(
    "/{simulation_path:path}/trials/{trial_id}/stderr",
    summary="Get tuner trial standard error",
    operation_id="getTunerTrialStderr",
    response_description="Text represented as a JSON string",
    responses=problems(404),
)
async def get_trial_stderr(
    service: TunerServiceDep, experiment_id: ExperimentIdPath, simulation_path: SimulationPath, trial_id: TrialId
) -> str:
    """Stderr log of a tuning trial."""
    return await service.trial_log(experiment_id, simulation_path, trial_id, "stderr")


@router.get(
    "/{simulation_path:path}",
    summary="Get a tuner job",
    operation_id="getTunerJob",
    response_description="Tuner job",
    responses=problems(404),
)
async def get_job(
    session: SessionDep, service: TunerServiceDep, experiment_id: ExperimentIdPath, simulation_path: SimulationPath
) -> TunerJobOut:
    """Get the tuner job of a simulation."""
    return await dump(session, TunerJobOut, await service.get(experiment_id, simulation_path, refresh=True))


@router.delete(
    "/{simulation_path:path}",
    status_code=HTTPStatus.NO_CONTENT,
    response_class=Response,
    summary="Delete a tuner job",
    operation_id="deleteTunerJob",
    response_description="Operation completed successfully",
    responses=problems(404),
)
async def delete_job(
    service: TunerServiceDep, experiment_id: ExperimentIdPath, simulation_path: SimulationPath
) -> None:
    """Delete a tuner job and its tuner-side resources."""
    await service.delete(experiment_id, simulation_path)
