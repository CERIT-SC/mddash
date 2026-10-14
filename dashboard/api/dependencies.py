"""
Request-scoped helpers shared by the routers.

Serialization reads ORM properties that parse engine logs and scan experiment
files, so it runs in a worker thread after the async refresh step fetched all
remote state. Values those properties cache on the rows are committed after.
"""

from collections.abc import Iterable, Sequence
from typing import Annotated, Any

import anyio
from db import get_session
from errors import NotFound
from fastapi import Depends, Path, Request
from models import Experiment
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from token_manager import MDRepoTokenManager

SessionDep = Annotated[AsyncSession, Depends(get_session)]
ExperimentIdPath = Annotated[str, Path(min_length=1)]


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


async def dump[M: BaseModel](session: AsyncSession, model: type[M], obj: object) -> M:
    """Serialize one ORM object off the event loop, then persist values cached on the rows."""
    result = await anyio.to_thread.run_sync(lambda: model.model_validate(obj, from_attributes=True))
    await session.commit()
    return result


async def dump_many[M: BaseModel](session: AsyncSession, model: type[M], objs: Iterable[Any]) -> list[M]:
    """Serialize ORM objects off the event loop, then persist values cached on the rows."""
    items = list(objs)
    result = await anyio.to_thread.run_sync(lambda: [model.model_validate(o, from_attributes=True) for o in items])
    await session.commit()
    return result
