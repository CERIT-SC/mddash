from http import HTTPStatus
from typing import Annotated

import anyio
from core.config import API_PREFIX
from core.dependencies import SessionDep
from core.responses import problems
from fastapi import APIRouter, Path, Response
from pydantic import TypeAdapter

from modules.experiments.dependencies import ExperimentDep
from modules.models import Simulation
from modules.simulations.schemas import Simulation as SimulationOut
from modules.simulations.schemas import SimulationWrite

router = APIRouter(prefix=f"{API_PREFIX}/experiments/{{experiment_id}}/simulations", tags=["Simulations"])

SimulationPath = Annotated[str, Path(min_length=1)]
_simulations = TypeAdapter(list[SimulationOut])


@router.get(
    "",
    summary="List simulation manifests",
    operation_id="listSimulations",
    response_description="Simulations",
    responses=problems(),
)
async def list_simulations(session: SessionDep, experiment: ExperimentDep) -> list[SimulationOut]:
    """List all simulations of an experiment."""
    await experiment.refresh_jobs()
    result = await anyio.to_thread.run_sync(
        lambda: _simulations.validate_python([s.to_dict() for s in Simulation.list(experiment.id, experiment)])
    )
    await session.commit()
    return result


@router.post(
    "",
    status_code=HTTPStatus.CREATED,
    summary="Create a simulation manifest",
    operation_id="createSimulation",
    response_description="Created simulation",
    responses=problems(400, 404, 409),
)
async def create_simulation(session: SessionDep, experiment: ExperimentDep, body: SimulationWrite) -> SimulationOut:
    """Create a new simulation manifest."""
    await experiment.refresh_jobs()
    result = await anyio.to_thread.run_sync(
        lambda: SimulationOut.model_validate(Simulation.write(experiment, body.model_dump()).to_dict())
    )
    await session.commit()
    return result


@router.get(
    "/{simulation_path:path}",
    summary="Get a simulation manifest",
    operation_id="getSimulation",
    response_description="Simulation",
    responses=problems(404),
)
async def get_simulation(
    session: SessionDep, experiment: ExperimentDep, simulation_path: SimulationPath
) -> SimulationOut:
    """Get a single simulation by its experiment-relative path."""
    await experiment.refresh_jobs()
    result = await anyio.to_thread.run_sync(
        lambda: SimulationOut.model_validate(Simulation.get(experiment.id, simulation_path, experiment).to_dict())
    )
    await session.commit()
    return result


@router.patch(
    "/{simulation_path:path}",
    summary="Update a simulation manifest",
    operation_id="updateSimulation",
    response_description="Updated simulation",
    responses=problems(400, 404, 409),
)
async def update_simulation(
    session: SessionDep, experiment: ExperimentDep, simulation_path: SimulationPath, body: SimulationWrite
) -> SimulationOut:
    """Edit an unlocked simulation manifest."""
    await experiment.refresh_jobs()
    result = await anyio.to_thread.run_sync(
        lambda: SimulationOut.model_validate(
            Simulation.update(experiment, simulation_path, body.model_dump()).to_dict()
        )
    )
    await session.commit()
    return result


@router.delete(
    "/{simulation_path:path}",
    status_code=HTTPStatus.NO_CONTENT,
    response_class=Response,
    summary="Delete a simulation manifest",
    operation_id="deleteSimulation",
    response_description="Operation completed successfully",
    responses=problems(400, 404),
)
async def delete_simulation(session: SessionDep, experiment: ExperimentDep, simulation_path: SimulationPath) -> None:
    """Delete a simulation manifest and cascade-delete all related jobs."""
    await Simulation.delete(session, experiment, simulation_path)
