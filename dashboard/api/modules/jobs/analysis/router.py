from http import HTTPStatus
from typing import Annotated

import anyio
from core.config import API_PREFIX
from core.dependencies import ExperimentIdPath, SessionDep, dump, dump_many
from core.enums import AnalysisType
from core.responses import problems
from fastapi import APIRouter, Path, Query, Response
from fastapi.responses import JSONResponse

from modules.experiments.dependencies import ExperimentDep
from modules.jobs.analysis.results import read_result, read_variants, result_names
from modules.jobs.analysis.schemas import AnalysisJob as AnalysisJobOut
from modules.jobs.analysis.schemas import AnalysisJobRequest, AnalysisResult, AnalysisVariant
from modules.jobs.analysis.service import AnalysisServiceDep

router = APIRouter(prefix=f"{API_PREFIX}/experiments/{{experiment_id}}/analysis", tags=["Analysis"])

JobId = Annotated[str, Path(min_length=1)]
ResultName = Annotated[str, Path(min_length=1)]
RequiredSimulationPath = Annotated[str, Query(min_length=1)]


@router.get(
    "",
    summary="List analysis jobs",
    operation_id="listAnalysisJobs",
    response_description="Analysis jobs",
    responses=problems(),
)
async def list_jobs(
    session: SessionDep,
    service: AnalysisServiceDep,
    experiment_id: ExperimentIdPath,
    simulation_path: Annotated[str | None, Query(min_length=1)] = None,
) -> list[AnalysisJobOut]:
    """List analysis jobs of an experiment, optionally only those of one simulation."""
    return await dump_many(session, AnalysisJobOut, await service.list_jobs(experiment_id, simulation_path))


@router.post(
    "",
    status_code=HTTPStatus.CREATED,
    summary="Submit an analysis job",
    operation_id="submitAnalysisJob",
    response_description="Submitted analysis job",
    responses=problems(400, 404),
)
async def submit_job(
    session: SessionDep, service: AnalysisServiceDep, experiment: ExperimentDep, body: AnalysisJobRequest
) -> AnalysisJobOut:
    """Submit an analysis job for a simulation's trajectory."""
    job = await service.submit(experiment, body.simulation_path, body.analysis, body.preprocessing_mode)
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
    return await anyio.to_thread.run_sync(result_names, experiment_id, simulation_path)


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
    return await anyio.to_thread.run_sync(read_variants, experiment_id, simulation_path, name)


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
    """Serve the JSON content of an analysis result file as-is."""
    return JSONResponse(await anyio.to_thread.run_sync(read_result, experiment_id, simulation_path, name))


@router.get(
    "/{job_id}/logs",
    summary="Get analysis job logs",
    operation_id="getAnalysisJobLogs",
    response_description="Text represented as a JSON string",
    responses=problems(404),
)
async def get_logs(
    service: AnalysisServiceDep,
    experiment_id: ExperimentIdPath,
    job_id: JobId,
    tail: Annotated[int, Query(ge=1, le=10_000)] = 200,
) -> str:
    """K8s pod logs of an analysis job, trimmed to start at the workflow start marker."""
    return await service.logs(experiment_id, job_id, tail)


@router.get(
    "/{job_id}",
    summary="Get an analysis job",
    operation_id="getAnalysisJob",
    response_description="Analysis job",
    responses=problems(404),
)
async def get_job(
    session: SessionDep, service: AnalysisServiceDep, experiment_id: ExperimentIdPath, job_id: JobId
) -> AnalysisJobOut:
    """Get an analysis job by ID."""
    return await dump(session, AnalysisJobOut, await service.get(experiment_id, job_id))


@router.delete(
    "/{job_id}",
    status_code=HTTPStatus.NO_CONTENT,
    response_class=Response,
    summary="Delete an analysis job",
    operation_id="deleteAnalysisJob",
    response_description="Operation completed successfully",
    responses=problems(404),
)
async def delete_job(service: AnalysisServiceDep, experiment_id: ExperimentIdPath, job_id: JobId) -> None:
    """Delete an analysis job and its temporary files."""
    await service.delete(experiment_id, job_id)
