"""Experiment lookups shared by the routers."""

from collections.abc import Iterable, Sequence
from typing import Annotated

from core.dependencies import ExperimentIdPath, SessionDep
from core.errors import NotFound
from fastapi import Depends, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from modules.mdrepo.tokens import MDRepoTokenManager
from modules.models import Experiment


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


async def list_experiments(session: AsyncSession) -> Sequence[Experiment]:
    """All experiments with their notebooks and jobs (relationships load eagerly)."""
    return (await session.execute(select(Experiment))).scalars().all()


async def mdrepo_token(request: Request, experiments: Iterable[Experiment]) -> str | None:
    """Session MDRepo token, fetched only when an experiment's MDRepo state is due for a sync."""
    manager = MDRepoTokenManager(request.session)
    if manager.has_session() and any(experiment.needs_mdrepo_sync() for experiment in experiments):
        return await manager.get_valid_token()
    return None
