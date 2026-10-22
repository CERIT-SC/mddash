from http import HTTPStatus
from typing import Annotated

from core.config import API_PREFIX
from core.dependencies import ExperimentIdPath, SessionDep, SimulationPath, dump, dump_many
from core.enums import DeviceType
from core.responses import problems
from fastapi import APIRouter, Query, Response

from modules.jobs.gmx.schemas import ExtendGromacsJobRequest, GromacsJobRequest
from modules.jobs.gmx.schemas import GromacsJob as GromacsJobOut
from modules.jobs.gmx.service import GromacsServiceDep

router = APIRouter(prefix=f"{API_PREFIX}/experiments/{{experiment_id}}/gmx", tags=["GROMACS"])


@router.get(
    "",
    summary="List GROMACS jobs",
    operation_id="listGromacsJobs",
    response_description="GROMACS jobs",
    responses=problems(),
)
async def list_jobs(
    session: SessionDep, service: GromacsServiceDep, experiment_id: ExperimentIdPath
) -> list[GromacsJobOut]:
    """List all GROMACS jobs of an experiment."""
    return await dump_many(session, GromacsJobOut, await service.list_jobs(experiment_id))


@router.post(
    "/{simulation_path:path}/stop",
    status_code=HTTPStatus.NO_CONTENT,
    response_class=Response,
    summary="Stop a GROMACS run, preserving its data",
    operation_id="stopGromacsJob",
    response_description="Operation completed successfully",
    responses=problems(400, 404),
)
async def stop_job(
    service: GromacsServiceDep, experiment_id: ExperimentIdPath, simulation_path: SimulationPath
) -> None:
    """Stop the run gracefully, keeping all data and the job row."""
    await service.stop(experiment_id, simulation_path)


@router.post(
    "/{simulation_path:path}/extend",
    status_code=HTTPStatus.CREATED,
    summary="Extend a finished or stopped GROMACS run from its checkpoint",
    operation_id="extendGromacsJob",
    response_description="Created GROMACS run extension",
    responses=problems(400, 404),
)
async def extend_job(
    session: SessionDep,
    service: GromacsServiceDep,
    experiment_id: ExperimentIdPath,
    simulation_path: SimulationPath,
    body: ExtendGromacsJobRequest,
) -> GromacsJobOut:
    """Extend a finished or stopped run by `nsteps` additional steps, resuming from its checkpoint."""
    job = await service.extend(experiment_id, simulation_path, body.nsteps)
    return await dump(session, GromacsJobOut, job)


@router.get(
    "/{simulation_path:path}/log",
    summary="Get a GROMACS job log",
    operation_id="getGromacsJobLog",
    response_description="Text represented as a JSON string",
    responses=problems(400, 404),
)
async def get_log(
    service: GromacsServiceDep,
    experiment_id: ExperimentIdPath,
    simulation_path: SimulationPath,
    log_type: Annotated[str, Query(alias="type")] = "gmx",
    tail: Annotated[int, Query(ge=1, le=100_000)] = 10_000,
) -> str:
    """Tail of one of the run's log streams (`gmx`, `stdout`, `stderr`)."""
    return await service.log(experiment_id, simulation_path, log_type, tail)


@router.get(
    "/{simulation_path:path}",
    summary="Get a GROMACS job",
    operation_id="getGromacsJob",
    response_description="GROMACS job",
    responses=problems(404),
)
async def get_job(
    session: SessionDep, service: GromacsServiceDep, experiment_id: ExperimentIdPath, simulation_path: SimulationPath
) -> GromacsJobOut:
    """Get the GROMACS run of a simulation."""
    return await dump(session, GromacsJobOut, await service.get(experiment_id, simulation_path))


@router.post(
    "/{simulation_path:path}",
    status_code=HTTPStatus.CREATED,
    summary="Submit a GROMACS job (replaces a terminal run, 409s on a live one)",
    operation_id="submitGromacsJob",
    response_description="Submitted GROMACS job",
    responses=problems(400, 404, 409),
)
async def submit_job(
    session: SessionDep,
    service: GromacsServiceDep,
    experiment_id: ExperimentIdPath,
    simulation_path: SimulationPath,
    body: GromacsJobRequest,
) -> GromacsJobOut:
    """Submit a GROMACS simulation job from a simulation manifest."""
    job = await service.submit(
        experiment_id, simulation_path, pme=DeviceType(body.pme), nb=DeviceType(body.nb), np=body.np, ntomp=body.ntomp
    )
    return await dump(session, GromacsJobOut, job)


@router.delete(
    "/{simulation_path:path}",
    status_code=HTTPStatus.NO_CONTENT,
    response_class=Response,
    summary="Delete a GROMACS job",
    operation_id="deleteGromacsJob",
    response_description="Operation completed successfully",
    responses=problems(404),
)
async def delete_job(
    service: GromacsServiceDep, experiment_id: ExperimentIdPath, simulation_path: SimulationPath
) -> None:
    """Delete the simulation's run: its MDRun job, DB row, and result files."""
    await service.delete(experiment_id, simulation_path)
