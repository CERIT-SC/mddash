"""Unit tests for the cancelling gather used by request fan-outs."""

import asyncio

import pytest
from core.concurrency import gather
from core.errors import NotFound


async def test_first_failure_cancels_siblings_and_propagates_unwrapped() -> None:
    sibling_finished = False

    async def slow_sibling() -> None:
        nonlocal sibling_finished
        await asyncio.sleep(1)
        sibling_finished = True

    async def failing() -> None:  # ruff:ignore[unused-async]
        raise NotFound("gone")

    with pytest.raises(NotFound, match="gone"):
        await gather(slow_sibling(), failing())
    assert not sibling_finished


async def test_runs_all_on_success() -> None:
    done: list[int] = []

    async def mark(value: int) -> None:  # ruff:ignore[unused-async]
        done.append(value)

    await gather(mark(1), mark(2))
    assert sorted(done) == [1, 2]
