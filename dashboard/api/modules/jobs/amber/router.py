from http import HTTPStatus
from typing import Annotated

from core.config import API_PREFIX
from core.dependencies import ExperimentIdPath, SessionDep, dump, dump_many
from core.errors import BadRequest
from core.responses import problems
from fastapi import APIRouter, Path, Query, Response

from modules.jobs.amber.schemas import AmberJob as AmberJobOut
from modules.jobs.amber.schemas import AmberJobRequest
from modules.jobs.amber.service import AmberServiceDep
from modules.simulations.manifest import check_simulation_path

router = APIRouter(prefix=f"{API_PREFIX}/experiments/{{experiment_id}}/amber", tags=["AMBER"])

SimulationPath = Annotated[str, Path(min_length=1)]


@router.get(
    "", summary="List AMBER jobs", operation_id="listAmberJobs", response_description="AMBER jobs", responses=problems()
)
async def list_jobs(
    session: SessionDep, service: AmberServiceDep, experiment_id: ExperimentIdPath
) -> list[AmberJobOut]:
    """List all AMBER jobs of an experiment."""
    return await dump_many(session, AmberJobOut, await service.list_jobs(experiment_id))


@router.post(
    "/{simulation_path:path}/stop",
    status_code=HTTPStatus.NO_CONTENT,
    response_class=Response,
    summary="Stop an AMBER run, preserving its data",
    operation_id="stopAmberJob",
    response_description="Operation completed successfully",
    responses=problems(400, 404),
)
async def stop_job(service: AmberServiceDep, experiment_id: ExperimentIdPath, simulation_path: SimulationPath) -> None:
    """Stop the run gracefully, keeping all data and the job row."""
    await service.stop(experiment_id, simulation_path)


@router.post(
    "/{simulation_path:path}/extend",
    summary="Extend an AMBER run (extension is GROMACS-only)",
    operation_id="extendAmberJob",
    response_model=None,
    responses=problems(400),
)
async def extend_job(
    experiment_id: ExperimentIdPath,  # ruff:ignore[unused-function-argument]
    simulation_path: SimulationPath,
) -> None:
    """
    Reject AMBER extension: it is GROMACS-only.

    Exists so that ``POST .../extend`` is a clear 400 instead of falling into the
    greedy submit route with confusing parameter errors.

    Raises:
        BadRequest: Always.
    """
    check_simulation_path(simulation_path)
    raise BadRequest("Simulation extension is only available for GROMACS.")


@router.get(
    "/{simulation_path:path}/log",
    summary="Get an AMBER job log",
    operation_id="getAmberJobLog",
    response_description="Text represented as a JSON string",
    responses=problems(400, 404),
)
async def get_log(
    service: AmberServiceDep,
    experiment_id: ExperimentIdPath,
    simulation_path: SimulationPath,
    log_type: Annotated[str, Query(alias="type")] = "mdout",
    tail: Annotated[int, Query(ge=1, le=100_000)] = 10_000,
) -> str:
    """Tail of one of the run's log streams (`mdout`, `mdinfo`, `stdout`, `stderr`)."""
    return await service.log(experiment_id, simulation_path, log_type, tail)


@router.get(
    "/{simulation_path:path}",
    summary="Get an AMBER job",
    operation_id="getAmberJob",
    response_description="AMBER job",
    responses=problems(404),
)
async def get_job(
    session: SessionDep, service: AmberServiceDep, experiment_id: ExperimentIdPath, simulation_path: SimulationPath
) -> AmberJobOut:
    """Get the AMBER run of a simulation."""
    return await dump(session, AmberJobOut, await service.get(experiment_id, simulation_path))


@router.post(
    "/{simulation_path:path}",
    status_code=HTTPStatus.CREATED,
    summary="Submit an AMBER job (replaces a terminal run, 409s on a live one)",
    operation_id="submitAmberJob",
    response_description="Submitted AMBER job",
    responses=problems(400, 404, 409),
)
async def submit_job(
    session: SessionDep,
    service: AmberServiceDep,
    experiment_id: ExperimentIdPath,
    simulation_path: SimulationPath,
    body: AmberJobRequest,
) -> AmberJobOut:
    """Submit an AMBER simulation job from a simulation manifest."""
    job = await service.submit(
        experiment_id, simulation_path, binary=body.binary, ewald=body.ewald, np=body.np, ntomp=body.ntomp
    )
    return await dump(session, AmberJobOut, job)


@router.delete(
    "/{simulation_path:path}",
    status_code=HTTPStatus.NO_CONTENT,
    response_class=Response,
    summary="Delete an AMBER job",
    operation_id="deleteAmberJob",
    response_description="Operation completed successfully",
    responses=problems(404),
)
async def delete_job(
    service: AmberServiceDep, experiment_id: ExperimentIdPath, simulation_path: SimulationPath
) -> None:
    """Delete the simulation's run: its MDRun job, DB row, and result files."""
    await service.delete(experiment_id, simulation_path)
