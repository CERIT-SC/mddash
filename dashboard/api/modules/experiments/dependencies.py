"""Experiment lookups shared by the routers."""

from typing import Annotated

from core.dependencies import ExperimentIdPath, SessionDep
from core.enums import PopulationStatus
from core.errors import Conflict, NotFound
from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from modules.experiments.models import Experiment

POPULATION_NOT_READY = "The experiment is not ready: its Datahugger repository import is not complete."


async def get_experiment_or_404(session: AsyncSession, experiment_id: str) -> Experiment:
    """
    Load an experiment with its notebook and jobs.

    Raises:
        NotFound: If the experiment does not exist.
    """
    experiment = await session.get(Experiment, experiment_id)
    if experiment is None:
        raise NotFound(f"Experiment {experiment_id} not found")
    return experiment


async def get_ready_experiment_or_404(session: AsyncSession, experiment_id: str) -> Experiment:
    """
    Load an experiment only when its Datahugger population is absent or already succeeded.

    The mutation guard for services that load the experiment internally;
    route-level callers use `ReadyExperimentDep`.

    Raises:
        Conflict: While its population is queued, running, cancelling, failed, or cancelled.
    """
    experiment = await get_experiment_or_404(session, experiment_id)
    if experiment.population is not None and experiment.population.status is not PopulationStatus.succeeded:
        raise Conflict(POPULATION_NOT_READY)
    return experiment


async def _experiment_dependency(session: SessionDep, experiment_id: ExperimentIdPath) -> Experiment:
    return await get_experiment_or_404(session, experiment_id)


ExperimentDep = Annotated[Experiment, Depends(_experiment_dependency)]


async def _ready_experiment_dependency(session: SessionDep, experiment_id: ExperimentIdPath) -> Experiment:
    return await get_ready_experiment_or_404(session, experiment_id)


ReadyExperimentDep = Annotated[Experiment, Depends(_ready_experiment_dependency)]
