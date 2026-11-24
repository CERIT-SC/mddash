from typing import Annotated

from core.config import API_PREFIX
from core.dependencies import SessionDep
from core.errors import NotFound
from core.responses import problems
from fastapi import APIRouter, Path

from modules.population.models import PopulationOperation
from modules.population.schemas import PopulationOperationStatus

router = APIRouter(prefix=f"{API_PREFIX}/experiment-population-jobs", tags=["Population"])


@router.get(
    "/{operation_id}",
    summary="Get a population operation",
    operation_id="getExperimentPopulationJob",
    response_description="Population operation status",
    responses=problems(404),
)
async def get_status(
    session: SessionDep, operation_id: Annotated[str, Path(min_length=1)]
) -> PopulationOperationStatus:
    """
    Read-only status of a Datahugger-NG population operation.

    Reconciliation (finalization and failure handling) is owned by the app
    lifespan monitor; this endpoint never mutates state.
    """
    operation = await session.get(PopulationOperation, operation_id)
    if operation is None:
        raise NotFound(f"Population operation {operation_id} not found")
    return PopulationOperationStatus(
        operation_id=operation.id,
        experiment_id=operation.experiment_id,
        status=operation.status.value,
        phase=operation.phase.value,
        files_present=operation.files_present,
        files_total=operation.files_total,
        bytes_present=operation.bytes_present,
        bytes_total=operation.bytes_total,
        byte_percentage=operation.byte_percentage,
        error=operation.error,
    )
