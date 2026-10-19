import asyncio
from http import HTTPStatus
from typing import Annotated

from clients import tuner
from core.config import API_PREFIX
from core.dependencies import ExperimentIdPath, SessionDep, dump, dump_many
from core.enums import Engine
from core.errors import NotFound
from core.responses import problems
from fastapi import APIRouter, Path, Response
from sqlalchemy.ext.asyncio import AsyncSession

from modules.experiments.dependencies import get_experiment_or_404
from modules.jobs.tuner.schemas import TunerJob as TunerJobOut
from modules.jobs.tuner.schemas import TunerJobRequest
from modules.models import TunerJob

router = APIRouter(prefix=f"{API_PREFIX}/experiments/{{experiment_id}}/tuner", tags=["Tuner"])

SimulationPath = Annotated[str, Path(min_length=1)]
TrialId = Annotated[str, Path(min_length=1)]


async def _find(session: AsyncSession, experiment_id: str, simulation_path: str) -> TunerJob | None:
    stmt = TunerJob.query().filter_by(experiment_id=experiment_id, simulation_path=simulation_path)
    return (await session.execute(stmt)).scalars().first()


async def _job_or_404(session: AsyncSession, experiment_id: str, simulation_path: str) -> TunerJob:
    job = await _find(session, experiment_id, simulation_path)
    if job is None:
        raise NotFound(f"Tuner job for {simulation_path} not found")
    return job


@router.get(
    "", summary="List tuner jobs", operation_id="listTunerJobs", response_description="Tuner jobs", responses=problems()
)
async def list_jobs(session: SessionDep, experiment_id: ExperimentIdPath) -> list[TunerJobOut]:
    """List all tuner jobs of an experiment."""
    jobs = (await session.execute(TunerJob.query().filter_by(experiment_id=experiment_id))).scalars().all()
    await asyncio.gather(*(job.refresh() for job in jobs))
    return await dump_many(session, TunerJobOut, jobs)


@router.post(
    "",
    status_code=HTTPStatus.CREATED,
    summary="Start a tuner job",
    operation_id="startTunerJob",
    response_description="Started tuner job",
    responses={200: {"model": TunerJobOut, "description": "Existing tuner job"}, **problems(400, 404)},
)
async def start_job(
    session: SessionDep, response: Response, experiment_id: ExperimentIdPath, body: TunerJobRequest
) -> TunerJobOut:
    """Start a tuner job for a simulation manifest; an existing healthy job is returned instead (200)."""
    experiment = await get_experiment_or_404(session, experiment_id)

    existing = await _find(session, experiment_id, body.simulation_path)
    if existing:
        if not existing.error_message:
            await existing.refresh()
            response.status_code = HTTPStatus.OK
            return await dump(session, TunerJobOut, existing)
        await existing.delete()
        await session.delete(existing)
        await session.commit()

    job = await TunerJob.start(session, experiment, body.simulation_path, nsteps=body.nsteps)
    await job.refresh()
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
async def stop_job(session: SessionDep, experiment_id: ExperimentIdPath, simulation_path: SimulationPath) -> None:
    """Stop a running tuner job, keeping its observed trials."""
    job = await _job_or_404(session, experiment_id, simulation_path)
    await job.stop()
    await session.commit()


async def _trial_log(
    session: AsyncSession, experiment_id: str, simulation_path: str, trial_id: str, stream: str
) -> str:
    job = await _job_or_404(session, experiment_id, simulation_path)
    match job.engine, stream:
        case Engine.GMX, "stdout":
            return await tuner.gmx_get_trial_stdout(job.id, trial_id)
        case Engine.GMX, _:
            return await tuner.gmx_get_trial_stderr(job.id, trial_id)
        case Engine.AMBER, "stdout":
            return await tuner.amber_get_trial_stdout(job.id, trial_id)
        case _:
            return await tuner.amber_get_trial_stderr(job.id, trial_id)


@router.get(
    "/{simulation_path:path}/trials/{trial_id}/stdout",
    summary="Get tuner trial standard output",
    operation_id="getTunerTrialStdout",
    response_description="Text represented as a JSON string",
    responses=problems(404),
)
async def get_trial_stdout(
    session: SessionDep, experiment_id: ExperimentIdPath, simulation_path: SimulationPath, trial_id: TrialId
) -> str:
    """Stdout log of a tuning trial."""
    return await _trial_log(session, experiment_id, simulation_path, trial_id, "stdout")


@router.get(
    "/{simulation_path:path}/trials/{trial_id}/stderr",
    summary="Get tuner trial standard error",
    operation_id="getTunerTrialStderr",
    response_description="Text represented as a JSON string",
    responses=problems(404),
)
async def get_trial_stderr(
    session: SessionDep, experiment_id: ExperimentIdPath, simulation_path: SimulationPath, trial_id: TrialId
) -> str:
    """Stderr log of a tuning trial."""
    return await _trial_log(session, experiment_id, simulation_path, trial_id, "stderr")


@router.get(
    "/{simulation_path:path}",
    summary="Get a tuner job",
    operation_id="getTunerJob",
    response_description="Tuner job",
    responses=problems(404),
)
async def get_job(session: SessionDep, experiment_id: ExperimentIdPath, simulation_path: SimulationPath) -> TunerJobOut:
    """Get the tuner job of a simulation."""
    job = await _job_or_404(session, experiment_id, simulation_path)
    await job.refresh()
    return await dump(session, TunerJobOut, job)


@router.delete(
    "/{simulation_path:path}",
    status_code=HTTPStatus.NO_CONTENT,
    response_class=Response,
    summary="Delete a tuner job",
    operation_id="deleteTunerJob",
    response_description="Operation completed successfully",
    responses=problems(404),
)
async def delete_job(session: SessionDep, experiment_id: ExperimentIdPath, simulation_path: SimulationPath) -> None:
    """Delete a tuner job and its tuner-side resources."""
    job = await _job_or_404(session, experiment_id, simulation_path)
    await job.delete()
    await session.delete(job)
    await session.commit()
