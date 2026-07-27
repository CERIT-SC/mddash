"""Engine-agnostic job management handlers — registered to each engine router."""

import logging
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Response
from fastapi.responses import PlainTextResponse
from fastapi.security import HTTPBasicCredentials
from sqlalchemy.exc import OperationalError
from starlette.concurrency import run_in_threadpool

from api.auth import verify_credentials
from api.db.operations import delete_job, get_job, get_trial
from api.rayworker import cancel_job
from api.schemas.common import MDEngine
from api.utils import cleanup_job_files, read_trial_log

logger = logging.getLogger(__name__)


async def _get_trial_log(
    job_id: str,
    trial_id: int,
    expected_engine: MDEngine,
    log_type: Literal["stdout", "stderr"],
) -> str:
    try:
        job = await run_in_threadpool(get_job, job_id)
        if not job or job.engine != expected_engine:
            raise HTTPException(status_code=404, detail=f"Job '{job_id}' not found")
        trial = await run_in_threadpool(get_trial, trial_id, job_id)
        if not trial:
            raise HTTPException(status_code=404, detail=f"Trial '{trial_id}' not found")
        return await run_in_threadpool(read_trial_log, job_id, str(trial_id), log_type)
    except OperationalError:
        logger.exception("Database timeout for job %s", job_id)
        raise HTTPException(status_code=503, detail="Database is busy. Please try again later.") from None


async def _delete_tuning_job(job_id: str, expected_engine: MDEngine) -> Response:
    """
    Cancel, delete from DB, and clean up files for a tuning job.

    Raises:
        HTTPException: 404 if the job is not found, 503 on DB timeout.
    """
    try:
        job = await run_in_threadpool(get_job, job_id)
        if not job or job.engine != expected_engine:
            raise HTTPException(status_code=404, detail=f"Job '{job_id}' not found")

        cancelled = await run_in_threadpool(cancel_job, job_id)
        await run_in_threadpool(delete_job, job_id)
        await run_in_threadpool(cleanup_job_files, job_id)

        logger.info("Deleted job %s: cancelled=%s", job_id, cancelled)
    except OperationalError:
        logger.exception("Database timeout for job %s", job_id)
        raise HTTPException(status_code=503, detail="Database is busy. Please try again later.") from None

    return Response(status_code=204)


def register_job_management_routes(router: APIRouter, engine: MDEngine) -> None:
    """Register engine-isolated log and delete routes on a router."""

    async def get_trial_stdout(
        job_id: str,
        trial_id: int,
        _: Annotated[HTTPBasicCredentials, Depends(verify_credentials)],
    ) -> str:
        return await _get_trial_log(job_id, trial_id, engine, "stdout")

    async def get_trial_stderr(
        job_id: str,
        trial_id: int,
        _: Annotated[HTTPBasicCredentials, Depends(verify_credentials)],
    ) -> str:
        return await _get_trial_log(job_id, trial_id, engine, "stderr")

    async def delete_tuning_job(
        job_id: str,
        _: Annotated[HTTPBasicCredentials, Depends(verify_credentials)],
    ) -> Response:
        return await _delete_tuning_job(job_id, engine)

    router.add_api_route(
        "/{job_id}/trials/{trial_id}/stdout",
        get_trial_stdout,
        methods=["GET"],
        response_class=PlainTextResponse,
        summary="Get trial stdout log",
    )
    router.add_api_route(
        "/{job_id}/trials/{trial_id}/stderr",
        get_trial_stderr,
        methods=["GET"],
        response_class=PlainTextResponse,
        summary="Get trial stderr log",
    )
    router.add_api_route(
        "/{job_id}",
        delete_tuning_job,
        methods=["DELETE"],
        status_code=204,
        summary="Delete a tuning job",
    )
