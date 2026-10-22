"""Experiment lookups shared by the routers."""

from typing import Annotated

from core.dependencies import ExperimentIdPath, SessionDep
from core.errors import NotFound
from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from modules.experiments.models import Experiment


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


async def _experiment_dependency(session: SessionDep, experiment_id: ExperimentIdPath) -> Experiment:
    return await get_experiment_or_404(session, experiment_id)


ExperimentDep = Annotated[Experiment, Depends(_experiment_dependency)]
