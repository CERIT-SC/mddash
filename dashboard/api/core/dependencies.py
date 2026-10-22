"""
Request-scoped helpers shared by the routers.

Serialization reads ORM properties that parse engine logs and scan experiment
files, so it runs in a worker thread after the async refresh step fetched all
remote state. Values those properties cache on the rows are committed after.
"""

from collections.abc import Iterable
from typing import Annotated, Any

import anyio
from clients import Clients
from fastapi import Depends, Path, Request
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from core.db import get_session


def get_clients(request: Request) -> Clients:
    """Upstream clients the app was built with."""
    return request.app.state.clients


SessionDep = Annotated[AsyncSession, Depends(get_session)]
ClientsDep = Annotated[Clients, Depends(get_clients)]
ExperimentIdPath = Annotated[str, Path(min_length=1)]
SimulationPath = Annotated[str, Path(min_length=1)]


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
