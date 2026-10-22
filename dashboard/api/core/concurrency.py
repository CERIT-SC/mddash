"""Structured fan-out for request work."""

import asyncio
from collections.abc import Coroutine
from typing import Any


async def gather(*coros: Coroutine[Any, Any, Any]) -> None:
    """
    Run `coros` concurrently; the first failure cancels the rest before it propagates.

    Unlike `asyncio.gather`, no sibling keeps mutating the request's ORM state
    after the error response. The first error is re-raised unwrapped so the
    problem-details handlers still see it.
    """
    try:
        async with asyncio.TaskGroup() as group:
            for coro in coros:
                group.create_task(coro)
    except ExceptionGroup as group_error:
        raise group_error.exceptions[0] from None
