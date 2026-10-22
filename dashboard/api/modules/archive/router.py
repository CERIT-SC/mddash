from http import HTTPStatus
from typing import cast

from core.config import API_PREFIX
from core.responses import problems
from fastapi import APIRouter

from modules.archive.schemas import ArchiveAttempt, ArchiveStatus
from modules.archive.service import ArchiveServiceDep
from modules.experiments.dependencies import ExperimentDep

router = APIRouter(prefix=f"{API_PREFIX}/experiments", tags=["Experiments"])


@router.post(
    "/{experiment_id}/archive",
    status_code=HTTPStatus.ACCEPTED,
    summary="Archive an experiment",
    description="Mirror the experiment to S3 at _archives/<id>/ and free the local PVC (verified before deletion).",
    operation_id="archiveExperiment",
    response_description="Archive accepted",
    responses=problems(400, 404, 409),
)
async def archive(experiment: ExperimentDep, service: ArchiveServiceDep) -> ArchiveAttempt:
    """Archive an experiment."""
    return {"attempt_id": await service.archive(experiment)}


@router.post(
    "/{experiment_id}/restore",
    status_code=HTTPStatus.ACCEPTED,
    summary="Restore an archived experiment",
    description="Copy the S3 archive back onto the local PVC and unfreeze the experiment.",
    operation_id="restoreExperiment",
    response_description="Restore accepted",
    responses=problems(400, 404, 409),
)
async def restore(experiment: ExperimentDep, service: ArchiveServiceDep) -> ArchiveAttempt:
    """Restore an archived experiment."""
    return {"attempt_id": await service.restore(experiment)}


@router.get(
    "/{experiment_id}/archive/status",
    summary="Get archive/restore status",
    operation_id="getArchiveStatus",
    response_description="Archive status",
    responses=problems(404),
)
async def archive_status(experiment: ExperimentDep, service: ArchiveServiceDep) -> ArchiveStatus:
    """Archive/restore status (status doc reconciled with live Jobs)."""
    return cast("ArchiveStatus", await service.status(experiment))
