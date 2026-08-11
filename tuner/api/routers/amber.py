"""AMBER tuning job endpoints — /api/tuning-jobs/amber."""

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
from api.engines.amber.config import AmberTrialConfig
from api.engines.amber.engine import AmberEngine
from api.rayworker import submit_tuning_job, sync_job_status
from api.routers._shared import register_job_management_routes
from api.schemas.amber import AmberJobStatusResponse, AmberTrialResponse
from api.schemas.common import JobCreatedResponse, JobStatus, MDEngine
from api.utils import AMBER_FORBIDDEN_FLAGS, cleanup_job_files, sanitize_extra_args, save_upload

logger = logging.getLogger(__name__)
router = APIRouter()

_INPCRD_EXTENSIONS = {".inpcrd", ".rst7", ".nc"}


def _validate_amber_file(file: UploadFile, allowed_extensions: set[str]) -> None:
    if file.size and file.size > MAX_UPLOAD_SIZE:
        raise HTTPException(status_code=413, detail=f"File size exceeds limit of {MAX_UPLOAD_SIZE} bytes")
    if not file.filename or not any(file.filename.endswith(ext) for ext in allowed_extensions):
        raise HTTPException(
            status_code=400,
            detail=f"File '{file.filename}' must have one of these extensions: {', '.join(sorted(allowed_extensions))}",
        )


@router.post("", status_code=201)
async def create_amber_tuning_job(
    _: Annotated[HTTPBasicCredentials, Depends(verify_credentials)],
    prmtop: Annotated[UploadFile, File()],
    inpcrd: Annotated[UploadFile, File()],
    mdin: Annotated[UploadFile, File()],
    nsteps: Annotated[int, Form(ge=1)] = 25_000,
    extra_args: Annotated[str, Form()] = "",
) -> JobCreatedResponse:
    """
    Start a new AMBER hyperparameter tuning run with prmtop + inpcrd + mdin.

    Raises:
        HTTPException: 400/413 on invalid input, 500 on submission failure.
    """
    try:
        sanitized_args = sanitize_extra_args(extra_args, AMBER_FORBIDDEN_FLAGS)
    except (ValidationError, ValueError) as e:
        raise HTTPException(status_code=400, detail=str(e)) from e

    _validate_amber_file(prmtop, {".prmtop", ".parm7"})
    _validate_amber_file(inpcrd, _INPCRD_EXTENSIONS)
    _validate_amber_file(mdin, {".mdin"})

    job_id = str(uuid.uuid4())
    try:
        await run_in_threadpool(save_upload, prmtop, INPUTS_DIR / f"{job_id}_md.prmtop")
        await run_in_threadpool(save_upload, inpcrd, INPUTS_DIR / f"{job_id}_md.inpcrd")
        await run_in_threadpool(save_upload, mdin, INPUTS_DIR / f"{job_id}_md.mdin")
        submit_tuning_job(job_id, AmberEngine(), MDEngine.AMBER, extra_args=sanitized_args, nsteps=nsteps)
    except Exception:
        logger.exception("Failed to create AMBER tuning job %s", job_id)
        await run_in_threadpool(cleanup_job_files, job_id)
        raise HTTPException(status_code=500, detail="Failed to submit tuning job.") from None

    logger.info("Started AMBER tuning job %s", job_id)
    return JobCreatedResponse(id=job_id, status=JobStatus.PENDING)


@router.get("/{job_id}/status")
async def get_amber_status(
    job_id: str, _: Annotated[HTTPBasicCredentials, Depends(verify_credentials)]
) -> AmberJobStatusResponse:
    """
    Get status of an AMBER tuning job.

    Raises:
        HTTPException: 404 if job not found or belongs to a different engine, 503 on DB timeout.
    """
    try:
        job = await run_in_threadpool(get_job, job_id)
        if not job or job.engine != MDEngine.AMBER:
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
        cfg = AmberTrialConfig.from_dict(t.config_json)
        estimated_time, estimated_cost = cfg.footprint.estimate(job.sim_length_ns, t.performance)
        trials.append(
            AmberTrialResponse(
                id=str(t.id),
                status=t.status,
                binary=cfg.binary.value,
                np=cfg.np,
                ntomp=cfg.ntomp,
                ewald=cfg.ewald.value,
                performance=t.performance,
                estimated_time=estimated_time,
                estimated_cost=estimated_cost,
            )
        )

    return AmberJobStatusResponse(
        id=job_id, status=job.status, error=job.error, sim_length_ns=job.sim_length_ns, trials=trials
    )


register_job_management_routes(router, MDEngine.AMBER)
