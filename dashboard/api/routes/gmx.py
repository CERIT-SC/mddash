import asyncio
from http import HTTPStatus
from typing import Annotated

import anyio
from config import API_PREFIX
from dependencies import ExperimentIdPath, SessionDep, dump, dump_many, get_experiment_or_404
from enums import DeviceType
from errors import BadRequest, Conflict, NotFound
from fastapi import APIRouter, Path, Query, Response
from models import GromacsJob
from models.simulation import check_simulation_path
from schemas.jobs import ExtendGromacsJobRequest, GromacsJobRequest
from schemas.jobs import GromacsJob as GromacsJobOut
from sqlalchemy.ext.asyncio import AsyncSession
from validators import check_log_type

from routes._responses import problems

router = APIRouter(prefix=f"{API_PREFIX}/experiments/{{experiment_id}}/gmx", tags=["GROMACS"])

SimulationPath = Annotated[str, Path(min_length=1)]


async def _job_or_404(
    session: AsyncSession, experiment_id: str, simulation_path: str, *, refresh: bool = True
) -> GromacsJob:
    """Return the simulation's single run row (status refreshed unless `refresh` is False)."""
    job = await GromacsJob.get(session, experiment_id, simulation_path)
    if job is None:
        raise NotFound(f"GROMACS job for simulation {simulation_path} in experiment {experiment_id} not found")
    if refresh:
        await job.refresh_status()
    return job


@router.get(
    "",
    summary="List GROMACS jobs",
    operation_id="listGromacsJobs",
    response_description="GROMACS jobs",
    responses=problems(),
)
async def list_jobs(session: SessionDep, experiment_id: ExperimentIdPath) -> list[GromacsJobOut]:
    """List all GROMACS jobs of an experiment."""
    jobs = (await session.execute(GromacsJob.query().filter_by(experiment_id=experiment_id))).scalars().all()
    await asyncio.gather(*(job.refresh_status() for job in jobs))
    return await dump_many(session, GromacsJobOut, jobs)


@router.post(
    "/{simulation_path:path}/stop",
    status_code=HTTPStatus.NO_CONTENT,
    response_class=Response,
    summary="Stop a GROMACS run, preserving its data",
    operation_id="stopGromacsJob",
    response_description="Operation completed successfully",
    responses=problems(400, 404),
)
async def stop_job(session: SessionDep, experiment_id: ExperimentIdPath, simulation_path: SimulationPath) -> None:
    """
    Stop the run gracefully, keeping all data and the job row.

    Raises:
        BadRequest: If the run is not live.
    """
    job = await _job_or_404(session, experiment_id, simulation_path)
    if not job.is_live:
        raise BadRequest("Only a live run can be stopped.")
    await job.stop()
    await session.commit()


@router.post(
    "/{simulation_path:path}/extend",
    status_code=HTTPStatus.CREATED,
    summary="Extend a finished or stopped GROMACS run from its checkpoint",
    operation_id="extendGromacsJob",
    response_description="Created GROMACS run extension",
    responses=problems(400, 404),
)
async def extend_job(
    session: SessionDep, experiment_id: ExperimentIdPath, simulation_path: SimulationPath, body: ExtendGromacsJobRequest
) -> GromacsJobOut:
    """Extend a finished or stopped run by `nsteps` additional steps, resuming from its checkpoint."""
    experiment = await get_experiment_or_404(session, experiment_id)
    job = await GromacsJob.extend(session, experiment=experiment, simulation_path=simulation_path, nsteps=body.nsteps)
    await job.refresh_status()
    return await dump(session, GromacsJobOut, job)


@router.get(
    "/{simulation_path:path}/log",
    summary="Get a GROMACS job log",
    operation_id="getGromacsJobLog",
    response_description="Text represented as a JSON string",
    responses=problems(400, 404),
)
async def get_log(
    session: SessionDep,
    experiment_id: ExperimentIdPath,
    simulation_path: SimulationPath,
    log_type: Annotated[str, Query(alias="type")] = "gmx",
    tail: Annotated[int, Query(ge=1, le=100_000)] = 10_000,
) -> str:
    """Tail of one of the run's log streams (`gmx`, `stdout`, `stderr`)."""
    job = await _job_or_404(session, experiment_id, simulation_path, refresh=False)
    log_type = log_type.lower()
    check_log_type(log_type)
    return await anyio.to_thread.run_sync(job.get_log, log_type, tail)


@router.get(
    "/{simulation_path:path}",
    summary="Get a GROMACS job",
    operation_id="getGromacsJob",
    response_description="GROMACS job",
    responses=problems(404),
)
async def get_job(
    session: SessionDep, experiment_id: ExperimentIdPath, simulation_path: SimulationPath
) -> GromacsJobOut:
    """Get the GROMACS run of a simulation."""
    return await dump(session, GromacsJobOut, await _job_or_404(session, experiment_id, simulation_path))


@router.post(
    "/{simulation_path:path}",
    status_code=HTTPStatus.CREATED,
    summary="Submit a GROMACS job (replaces a terminal run, 409s on a live one)",
    operation_id="submitGromacsJob",
    response_description="Submitted GROMACS job",
    responses=problems(400, 404, 409),
)
async def submit_job(
    session: SessionDep, experiment_id: ExperimentIdPath, simulation_path: SimulationPath, body: GromacsJobRequest
) -> GromacsJobOut:
    """
    Submit a GROMACS simulation job from a simulation manifest.

    Raises:
        Conflict: If a live run already exists for this simulation.
    """
    check_simulation_path(simulation_path)
    experiment = await get_experiment_or_404(session, experiment_id)

    prior = await GromacsJob.get(session, experiment_id, simulation_path)
    if prior is not None:
        await prior.refresh_status()
        if prior.is_live:
            raise Conflict("A run is already active for this simulation; stop it first to submit a new run.")

    # A terminal run (finished, stopped, or failed) is replaced by the new one.
    await GromacsJob.remove(session, experiment_id, simulation_path)

    job = await GromacsJob.start(
        session,
        experiment=experiment,
        simulation_path=simulation_path,
        pme=DeviceType(body.pme),
        nb=DeviceType(body.nb),
        np=body.np,
        ntomp=body.ntomp,
    )
    await job.refresh_status()
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
async def delete_job(session: SessionDep, experiment_id: ExperimentIdPath, simulation_path: SimulationPath) -> None:
    """Delete the simulation's run: its MDRun job, DB row, and result files."""
    if not await GromacsJob.remove(session, experiment_id, simulation_path):
        raise NotFound(f"GROMACS job for simulation {simulation_path} in experiment {experiment_id} not found")
