import asyncio
import json
from http import HTTPStatus
from pathlib import Path as FilePath
from typing import Annotated, Any

import anyio
from clients import k8s
from config import API_PREFIX
from dependencies import ExperimentDep, ExperimentIdPath, SessionDep, dump, dump_many
from enums import AnalysisType, Engine, PreprocessingMode
from errors import BadRequest, NotFound, UnprocessableEntity
from fastapi import APIRouter, Path, Query, Response
from fastapi.responses import JSONResponse
from models import AnalysisJob, Experiment
from models.analysis_job import ANALYSIS_RESULT_PREFIX, ANALYSIS_RESULT_SUFFIX, find_result_file, list_result_files
from models.simulation import Simulation
from schemas.analysis import AnalysisResult
from schemas.jobs import AnalysisJob as AnalysisJobOut
from schemas.jobs import AnalysisJobRequest, AnalysisVariant
from sqlalchemy.ext.asyncio import AsyncSession

from routes._responses import problems

router = APIRouter(prefix=f"{API_PREFIX}/experiments/{{experiment_id}}/analysis", tags=["Analysis"])

JobId = Annotated[str, Path(min_length=1)]
ResultName = Annotated[str, Path(min_length=1)]
RequiredSimulationPath = Annotated[str, Query(min_length=1)]

# The MDDB workflow prints container setup noise before this line.
_WORKFLOW_START_MARKER = "Running MDDB workflow"


async def _job_or_404(session: AsyncSession, experiment_id: str, job_id: str) -> AnalysisJob:
    stmt = AnalysisJob.query().filter_by(experiment_id=experiment_id, id=job_id)
    job = (await session.execute(stmt)).scalars().first()
    if job is None:
        raise NotFound(f"Analysis job {job_id} in experiment {experiment_id} not found")
    return job


def _read_json(path: FilePath) -> Any:  # ruff:ignore[any-type]
    return json.loads(path.read_text(encoding="utf-8"))


@router.get(
    "",
    summary="List analysis jobs",
    operation_id="listAnalysisJobs",
    response_description="Analysis jobs",
    responses=problems(),
)
async def list_jobs(
    session: SessionDep,
    experiment_id: ExperimentIdPath,
    simulation_path: Annotated[str | None, Query(min_length=1)] = None,
) -> list[AnalysisJobOut]:
    """List analysis jobs of an experiment, optionally only those of one simulation."""
    stmt = AnalysisJob.query().filter_by(experiment_id=experiment_id)
    if simulation_path:
        stmt = stmt.filter_by(simulation_path=simulation_path)
    jobs = (await session.execute(stmt)).scalars().all()
    await asyncio.gather(*(job.refresh_status() for job in jobs))
    return await dump_many(session, AnalysisJobOut, jobs)


def _analysis_inputs(
    experiment: Experiment, simulation_path: str, preprocessing_mode: PreprocessingMode
) -> tuple[FilePath, FilePath | None, FilePath | None]:
    """Resolve (trajectory, structure, topology) for an analysis; sync (manifest and file checks)."""
    simulation = Simulation.get(experiment.id, simulation_path, experiment)
    simulation.require_files(["trajectory"])
    trajectory_path = simulation.resolve_role("trajectory")
    if not trajectory_path.is_file():
        raise BadRequest(f"Trajectory file {trajectory_path} does not exist.")

    topology_path: FilePath | None = None
    if experiment.engine == Engine.GMX and "run_input" in simulation.files:
        topology_path = simulation.resolve_role("run_input")
    elif "topology" in simulation.files:
        topology_path = simulation.resolve_role("topology")

    structure_path: FilePath | None = None
    if "reference_structure" in simulation.files:
        structure_path = simulation.resolve_role("reference_structure")

    if preprocessing_mode in {PreprocessingMode.IMAGE, PreprocessingMode.IMAGE_FIT} and (
        not topology_path or topology_path.suffix.lower() != ".tpr"
    ):
        raise BadRequest("Trajectory preprocessing requires a simulation TPR file (.tpr).")

    if experiment.engine == Engine.GMX and preprocessing_mode is PreprocessingMode.AS_IS and structure_path is not None:
        topology_path = None
    return trajectory_path, structure_path, topology_path


@router.post(
    "",
    status_code=HTTPStatus.CREATED,
    summary="Submit an analysis job",
    operation_id="submitAnalysisJob",
    response_description="Submitted analysis job",
    responses=problems(400, 404),
)
async def submit_job(session: SessionDep, experiment: ExperimentDep, body: AnalysisJobRequest) -> AnalysisJobOut:
    """Submit an analysis job for a simulation's trajectory."""
    trajectory, structure, topology = await anyio.to_thread.run_sync(
        _analysis_inputs, experiment, body.simulation_path, body.preprocessing_mode
    )
    job = await AnalysisJob.start(
        session,
        experiment=experiment,
        simulation_path=body.simulation_path,
        analysis_name=body.analysis,
        structure_file=structure,
        trajectory_file=trajectory,
        topology_file=topology,
        preprocessing_mode=body.preprocessing_mode,
    )
    await job.refresh_status()
    return await dump(session, AnalysisJobOut, job)


@router.get(
    "/types",
    summary="List supported analysis types",
    description="The hard set of mwf analysis task names derived from the MDDB workflow — the pool of analyses a simulation can produce.",
    operation_id="listAnalysisTypes",
    response_description="Analysis type ids",
    responses=problems(),
)
async def list_types(experiment_id: ExperimentIdPath) -> list[str]:  # ruff:ignore[unused-function-argument]
    """List the mwf analysis task names the dashboard supports (experiment-independent)."""
    return [analysis_type.value for analysis_type in AnalysisType]


@router.get(
    "/results",
    summary="List available analysis results",
    operation_id="listAnalysisResults",
    response_description="Normalized analysis result names",
    responses=problems(400),
)
async def list_results(experiment_id: ExperimentIdPath, simulation_path: RequiredSimulationPath) -> list[str]:
    """Names of the analysis results available for a simulation."""
    files = await anyio.to_thread.run_sync(list_result_files, experiment_id, simulation_path)
    return [f.name[len(ANALYSIS_RESULT_PREFIX) : -len(ANALYSIS_RESULT_SUFFIX)].replace("_", "-") for f in files]


@router.get(
    "/results/{name}/variants",
    summary="List variants for an analysis result",
    operation_id="listAnalysisResultVariants",
    response_description="Analysis variants",
    responses=problems(400),
)
async def get_variants(
    experiment_id: ExperimentIdPath, name: ResultName, simulation_path: RequiredSimulationPath
) -> list[AnalysisVariant]:
    """Variant options of a multi-file analysis from its summary JSON (empty when absent or not a summary)."""
    result_file = await anyio.to_thread.run_sync(find_result_file, experiment_id, simulation_path, name)
    if not result_file:
        return []
    try:
        data = await anyio.to_thread.run_sync(_read_json, result_file)
    except (json.JSONDecodeError, UnicodeDecodeError):
        return []
    if isinstance(data, list) and all(
        isinstance(item, dict) and "analysis" in item and "name" in item for item in data
    ):
        return data
    return []


@router.get(
    "/results/{name}",
    summary="Get a typed analysis result",
    operation_id="getAnalysisResult",
    response_model=None,
    responses={
        200: {"model": AnalysisResult, "description": "Supported MWF analysis result"},
        **problems(400, 404, 422),
    },
)
async def get_result(
    experiment_id: ExperimentIdPath, name: ResultName, simulation_path: RequiredSimulationPath
) -> JSONResponse:
    """
    Serve the JSON content of an analysis result file as-is.

    Raises:
        NotFound: If the analysis result file does not exist.
        UnprocessableEntity: If the result file cannot be parsed as JSON.
    """
    result_file = await anyio.to_thread.run_sync(find_result_file, experiment_id, simulation_path, name)
    if not result_file:
        raise NotFound(f"Analysis result '{name}' not found.")
    try:
        data = await anyio.to_thread.run_sync(_read_json, result_file)
    except (json.JSONDecodeError, UnicodeDecodeError) as e:
        raise UnprocessableEntity("Failed to read analysis result.") from e
    return JSONResponse(data)


@router.get(
    "/{job_id}/logs",
    summary="Get analysis job logs",
    operation_id="getAnalysisJobLogs",
    response_description="Text represented as a JSON string",
    responses=problems(404),
)
async def get_logs(
    session: SessionDep,
    experiment_id: ExperimentIdPath,
    job_id: JobId,
    tail: Annotated[int, Query(ge=1, le=10_000)] = 200,
) -> str:
    """K8s pod logs of an analysis job, trimmed to start at the workflow start marker."""
    job = await _job_or_404(session, experiment_id, job_id)
    logs = await k8s.get_job_logs(f"analysis-{job.id}", tail_lines=tail)
    idx = logs.find(_WORKFLOW_START_MARKER)
    return logs[idx:] if idx != -1 else logs


@router.get(
    "/{job_id}",
    summary="Get an analysis job",
    operation_id="getAnalysisJob",
    response_description="Analysis job",
    responses=problems(404),
)
async def get_job(session: SessionDep, experiment_id: ExperimentIdPath, job_id: JobId) -> AnalysisJobOut:
    """Get an analysis job by ID."""
    job = await _job_or_404(session, experiment_id, job_id)
    await job.refresh_status()
    return await dump(session, AnalysisJobOut, job)


@router.delete(
    "/{job_id}",
    status_code=HTTPStatus.NO_CONTENT,
    response_class=Response,
    summary="Delete an analysis job",
    operation_id="deleteAnalysisJob",
    response_description="Operation completed successfully",
    responses=problems(404),
)
async def delete_job(session: SessionDep, experiment_id: ExperimentIdPath, job_id: JobId) -> None:
    """Delete an analysis job and its temporary files."""
    job = await _job_or_404(session, experiment_id, job_id)
    await job.delete()
    await session.delete(job)
    await session.commit()
