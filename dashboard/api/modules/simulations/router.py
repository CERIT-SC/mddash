from http import HTTPStatus

from core.config import API_PREFIX
from core.dependencies import SessionDep, SimulationPath, dump, dump_many
from core.responses import problems
from fastapi import APIRouter, Response

from modules.experiments.dependencies import ExperimentDep
from modules.simulations.schemas import Simulation as SimulationOut
from modules.simulations.schemas import SimulationWrite
from modules.simulations.service import SimulationServiceDep

router = APIRouter(prefix=f"{API_PREFIX}/experiments/{{experiment_id}}/simulations", tags=["Simulations"])


@router.get(
    "",
    summary="List simulation manifests",
    operation_id="listSimulations",
    response_description="Simulations",
    responses=problems(),
)
async def list_simulations(
    session: SessionDep, experiment: ExperimentDep, service: SimulationServiceDep
) -> list[SimulationOut]:
    """List all simulations of an experiment."""
    return await dump_many(session, SimulationOut, await service.list_simulations(experiment))


@router.post(
    "",
    status_code=HTTPStatus.CREATED,
    summary="Create a simulation manifest",
    operation_id="createSimulation",
    response_description="Created simulation",
    responses=problems(400, 404, 409),
)
async def create_simulation(
    session: SessionDep, experiment: ExperimentDep, service: SimulationServiceDep, body: SimulationWrite
) -> SimulationOut:
    """Create a new simulation manifest."""
    return await dump(session, SimulationOut, await service.create(experiment, body.model_dump()))


@router.get(
    "/{simulation_path:path}",
    summary="Get a simulation manifest",
    operation_id="getSimulation",
    response_description="Simulation",
    responses=problems(404),
)
async def get_simulation(
    session: SessionDep, experiment: ExperimentDep, service: SimulationServiceDep, simulation_path: SimulationPath
) -> SimulationOut:
    """Get a single simulation by its experiment-relative path."""
    return await dump(session, SimulationOut, await service.get(experiment, simulation_path))


@router.patch(
    "/{simulation_path:path}",
    summary="Update a simulation manifest",
    operation_id="updateSimulation",
    response_description="Updated simulation",
    responses=problems(400, 404, 409),
)
async def update_simulation(
    session: SessionDep,
    experiment: ExperimentDep,
    service: SimulationServiceDep,
    simulation_path: SimulationPath,
    body: SimulationWrite,
) -> SimulationOut:
    """Edit an unlocked simulation manifest."""
    return await dump(session, SimulationOut, await service.update(experiment, simulation_path, body.model_dump()))


@router.delete(
    "/{simulation_path:path}",
    status_code=HTTPStatus.NO_CONTENT,
    response_class=Response,
    summary="Delete a simulation manifest",
    operation_id="deleteSimulation",
    response_description="Operation completed successfully",
    responses=problems(400, 404),
)
async def delete_simulation(
    experiment: ExperimentDep, service: SimulationServiceDep, simulation_path: SimulationPath
) -> None:
    """Delete a simulation manifest and cascade-delete all related jobs."""
    await service.delete(experiment, simulation_path)
