from http import HTTPStatus

from core.config import API_PREFIX
from core.dependencies import SessionDep
from core.responses import problems
from fastapi import APIRouter
from pydantic import TypeAdapter

from modules.archive.schemas import ArchiveAttempt, ArchiveStatus
from modules.experiments.dependencies import ExperimentDep

router = APIRouter(prefix=f"{API_PREFIX}/experiments", tags=["Experiments"])

_archive_status = TypeAdapter(ArchiveStatus)


@router.post(
    "/{experiment_id}/archive",
    status_code=HTTPStatus.ACCEPTED,
    summary="Archive an experiment",
    description="Mirror the experiment to S3 at _archives/<id>/ and free the local PVC (verified before deletion).",
    operation_id="archiveExperiment",
    response_description="Archive accepted",
    responses=problems(400, 404, 409),
)
async def archive(session: SessionDep, experiment: ExperimentDep) -> ArchiveAttempt:
    """Archive an experiment."""
    attempt_id = await experiment.archive(session)
    return {"attempt_id": attempt_id}


@router.post(
    "/{experiment_id}/restore",
    status_code=HTTPStatus.ACCEPTED,
    summary="Restore an archived experiment",
    description="Copy the S3 archive back onto the local PVC and unfreeze the experiment.",
    operation_id="restoreExperiment",
    response_description="Restore accepted",
    responses=problems(400, 404, 409),
)
async def restore(session: SessionDep, experiment: ExperimentDep) -> ArchiveAttempt:
    """Restore an archived experiment."""
    attempt_id = await experiment.restore()
    await session.commit()
    return {"attempt_id": attempt_id}


@router.get(
    "/{experiment_id}/archive/status",
    summary="Get archive/restore status",
    operation_id="getArchiveStatus",
    response_description="Archive status",
    responses=problems(404),
)
async def archive_status(session: SessionDep, experiment: ExperimentDep) -> ArchiveStatus:
    """Archive/restore status (status doc reconciled with live Jobs)."""
    status = await experiment.get_archive_status()
    await session.commit()
    return _archive_status.validate_python(status)
