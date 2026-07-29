"""GMX tuning job endpoints — /api/tuning-jobs/gmx."""

import logging
import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.security import HTTPBasicCredentials
from pydantic import ValidationError
from sqlalchemy.exc import OperationalError
from starlette.concurrency import run_in_threadpool

from api.auth import verify_credentials
from api.config import INPUTS_DIR, MAX_UPLOAD_SIZE
from api.db.operations import get_job, get_trials_by_job_id
from api.engines.gmx.config import GmxTrialConfig
from api.engines.gmx.engine import GmxEngine
from api.rayworker import submit_tuning_job, sync_job_status
from api.routers._shared import register_job_management_routes
from api.schemas.common import JobCreatedResponse, JobStatus, MDEngine
from api.schemas.gmx import GmxJobStatusResponse, GmxTrialResponse
from api.utils import GMX_FORBIDDEN_FLAGS, cleanup_job_files, extract_nsteps_override, sanitize_extra_args, save_upload

logger = logging.getLogger(__name__)
router = APIRouter()


@router.post("", status_code=201)
async def create_gmx_tuning_job(
    _: Annotated[HTTPBasicCredentials, Depends(verify_credentials)],
    file: Annotated[UploadFile, File()],
    nsteps: Annotated[int, Form(ge=1)] = 25_000,
    extra_args: Annotated[str, Form()] = "",
) -> JobCreatedResponse:
    """
    Start a new GMX hyperparameter tuning run with a .tpr file.

    Raises:
        HTTPException: 400/413 on invalid input, 500 on submission failure.
    """
    try:
        benchmark_args, nsteps_override = extract_nsteps_override(extra_args)
        sanitized_args = sanitize_extra_args(benchmark_args, GMX_FORBIDDEN_FLAGS)
    except (ValidationError, ValueError) as e:
        raise HTTPException(status_code=400, detail=str(e)) from e

    if file.size and file.size > MAX_UPLOAD_SIZE:
        raise HTTPException(status_code=413, detail=f"File size exceeds limit of {MAX_UPLOAD_SIZE} bytes")
    if not file.filename or not file.filename.endswith(".tpr"):
        raise HTTPException(status_code=400, detail="Only .tpr files are allowed")

    job_id = str(uuid.uuid4())
    try:
        await run_in_threadpool(save_upload, file, INPUTS_DIR / f"{job_id}_md.tpr")
        submit_tuning_job(
            job_id, GmxEngine(), MDEngine.GMX, extra_args=sanitized_args, nsteps=nsteps, nsteps_override=nsteps_override
        )
    except Exception as e:
        logger.exception("Failed to create GMX tuning job %s", job_id)
        await run_in_threadpool(cleanup_job_files, job_id)
        raise HTTPException(status_code=500, detail=f"Failed to submit job: {e}") from e

    logger.info("Started GMX tuning job %s", job_id)
    return JobCreatedResponse(id=job_id, status=JobStatus.PENDING)


@router.get("/{job_id}/status")
async def get_gmx_status(
    job_id: str, _: Annotated[HTTPBasicCredentials, Depends(verify_credentials)]
) -> GmxJobStatusResponse:
    """
    Get status of a GMX tuning job.

    Raises:
        HTTPException: 404 if job not found or belongs to a different engine, 503 on DB timeout.
    """
    try:
        job = await run_in_threadpool(get_job, job_id)
        if not job or job.engine != MDEngine.GMX:
            raise HTTPException(status_code=404, detail=f"Job '{job_id}' not found")
        await run_in_threadpool(sync_job_status, job_id)
        job = await run_in_threadpool(get_job, job_id)
        if not job:
            raise HTTPException(status_code=404, detail=f"Job '{job_id}' not found")
        raw_trials = await run_in_threadpool(get_trials_by_job_id, job_id)
    except OperationalError as e:
        logger.exception("Database timeout for job %s", job_id)
        raise HTTPException(status_code=503, detail="Database is busy. Please try again later.") from e

    trials = []
    for t in raw_trials:
        cfg = GmxTrialConfig.from_dict(t.config_json)
        estimated_time, estimated_cost = cfg.footprint.estimate(job.sim_length_ns, t.performance)
        trials.append(
            GmxTrialResponse(
                id=str(t.id),
                status=t.status,
                ntomp=cfg.ntomp,
                np=cfg.np,
                nb=cfg.nb.value,
                pme=cfg.pme.value,
                performance=t.performance,
                estimated_time=estimated_time,
                estimated_cost=estimated_cost,
            )
        )

    return GmxJobStatusResponse(
        id=job_id, status=job.status, error=job.error, sim_length_ns=job.sim_length_ns, trials=trials
    )


register_job_management_routes(router, MDEngine.GMX)
