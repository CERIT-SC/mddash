import asyncio
from http import HTTPStatus
from typing import Annotated

import anyio
from core.config import API_PREFIX
from core.dependencies import ExperimentIdPath, SessionDep, dump, dump_many
from core.enums import AmberBinary, EwaldPreset
from core.errors import BadRequest, Conflict, NotFound
from core.responses import problems
from fastapi import APIRouter, Path, Query, Response
from sqlalchemy.ext.asyncio import AsyncSession

from modules.experiments.dependencies import get_experiment_or_404
from modules.jobs.amber.schemas import AmberJob as AmberJobOut
from modules.jobs.amber.schemas import AmberJobRequest
from modules.models import AmberJob
from modules.simulations.manifest import check_simulation_path

router = APIRouter(prefix=f"{API_PREFIX}/experiments/{{experiment_id}}/amber", tags=["AMBER"])

SimulationPath = Annotated[str, Path(min_length=1)]


async def _job_or_404(
    session: AsyncSession, experiment_id: str, simulation_path: str, *, refresh: bool = True
) -> AmberJob:
    """Return the simulation's single run row (status refreshed unless `refresh` is False)."""
    job = await AmberJob.get(session, experiment_id, simulation_path)
    if job is None:
        raise NotFound(f"AMBER job for simulation {simulation_path} in experiment {experiment_id} not found")
    if refresh:
        await job.refresh_status()
    return job


@router.get(
    "", summary="List AMBER jobs", operation_id="listAmberJobs", response_description="AMBER jobs", responses=problems()
)
async def list_jobs(session: SessionDep, experiment_id: ExperimentIdPath) -> list[AmberJobOut]:
    """List all AMBER jobs of an experiment."""
    jobs = (await session.execute(AmberJob.query().filter_by(experiment_id=experiment_id))).scalars().all()
    await asyncio.gather(*(job.refresh_status() for job in jobs))
    return await dump_many(session, AmberJobOut, jobs)


@router.post(
    "/{simulation_path:path}/stop",
    status_code=HTTPStatus.NO_CONTENT,
    response_class=Response,
    summary="Stop an AMBER run, preserving its data",
    operation_id="stopAmberJob",
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
    session: SessionDep,
    experiment_id: ExperimentIdPath,
    simulation_path: SimulationPath,
    log_type: Annotated[str, Query(alias="type")] = "mdout",
    tail: Annotated[int, Query(ge=1, le=100_000)] = 10_000,
) -> str:
    """Tail of one of the run's log streams (`mdout`, `mdinfo`, `stdout`, `stderr`)."""
    job = await _job_or_404(session, experiment_id, simulation_path, refresh=False)
    return await anyio.to_thread.run_sync(job.get_log, log_type.lower(), tail)


@router.get(
    "/{simulation_path:path}",
    summary="Get an AMBER job",
    operation_id="getAmberJob",
    response_description="AMBER job",
    responses=problems(404),
)
async def get_job(session: SessionDep, experiment_id: ExperimentIdPath, simulation_path: SimulationPath) -> AmberJobOut:
    """Get the AMBER run of a simulation."""
    return await dump(session, AmberJobOut, await _job_or_404(session, experiment_id, simulation_path))


@router.post(
    "/{simulation_path:path}",
    status_code=HTTPStatus.CREATED,
    summary="Submit an AMBER job (replaces a terminal run, 409s on a live one)",
    operation_id="submitAmberJob",
    response_description="Submitted AMBER job",
    responses=problems(400, 404, 409),
)
async def submit_job(
    session: SessionDep, experiment_id: ExperimentIdPath, simulation_path: SimulationPath, body: AmberJobRequest
) -> AmberJobOut:
    """
    Submit an AMBER simulation job from a simulation manifest.

    Raises:
        BadRequest: If the binary or Ewald preset is unknown.
        Conflict: If a live run already exists for this simulation.
    """
    check_simulation_path(simulation_path)
    experiment = await get_experiment_or_404(session, experiment_id)

    prior = await AmberJob.get(session, experiment_id, simulation_path)
    if prior is not None:
        await prior.refresh_status()
        if prior.is_live:
            raise Conflict("A run is already active for this simulation; stop it first to submit a new run.")

    try:
        binary = AmberBinary.from_string(body.binary)
        ewald = EwaldPreset.from_string(body.ewald)
    except ValueError as exc:
        raise BadRequest("Invalid compute parameters.") from exc

    # A terminal run (finished, stopped, or failed) is replaced by the new one.
    await AmberJob.remove(session, experiment_id, simulation_path)

    job = await AmberJob.start(
        session,
        experiment=experiment,
        simulation_path=simulation_path,
        binary=binary,
        ewald=ewald,
        np=body.np,
        ntomp=body.ntomp,
    )
    await job.refresh_status()
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
async def delete_job(session: SessionDep, experiment_id: ExperimentIdPath, simulation_path: SimulationPath) -> None:
    """Delete the simulation's run: its MDRun job, DB row, and result files."""
    if not await AmberJob.remove(session, experiment_id, simulation_path):
        raise NotFound(f"AMBER job for simulation {simulation_path} in experiment {experiment_id} not found")
