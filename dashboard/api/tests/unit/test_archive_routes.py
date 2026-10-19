"""Unit tests for archive/restore routes."""

from unittest.mock import AsyncMock, patch

import pytest
from core.errors import ApiError, Conflict
from httpx import AsyncClient
from modules.models import Experiment, Notebook
from sqlalchemy.ext.asyncio import AsyncSession


@pytest.fixture(autouse=True)
async def _experiment(db_session: AsyncSession) -> None:
    db_session.add(Experiment(id="abcde", name="Archive Routes"))
    db_session.add(Notebook(experiment_id="abcde"))
    await db_session.commit()


class TestArchiveRoute:
    async def test_conflicts_surface_as_409_problem(self, client: AsyncClient) -> None:
        with patch.object(Experiment, "archive", AsyncMock(side_effect=Conflict("live jobs running"))):
            response = await client.post("/dash/api/experiments/abcde/archive")

        assert response.status_code == 409
        assert response.headers["content-type"] == "application/problem+json"
        assert response.json()["detail"] == "live jobs running"

    async def test_gate_conflicts_carry_the_contract_token(self, client: AsyncClient) -> None:
        error = ApiError(409, "live jobs running", "urn:mddash:archive-conflict")
        with patch.object(Experiment, "archive", AsyncMock(side_effect=error)):
            response = await client.post("/dash/api/experiments/abcde/archive")

        assert response.status_code == 409
        body = response.json()
        assert body["type"] == "urn:mddash:archive-conflict"
        assert "solution" not in body  # conflict details already imply the fix

    async def test_success_returns_202(self, client: AsyncClient) -> None:
        with patch.object(Experiment, "archive", AsyncMock(return_value="attempt-1")):
            response = await client.post("/dash/api/experiments/abcde/archive")

        assert response.status_code == 202
        assert response.json()["attempt_id"] == "attempt-1"

    async def test_missing_experiment_is_404(self, client: AsyncClient) -> None:
        response = await client.post("/dash/api/experiments/zzzzz/archive")
        assert response.status_code == 404


class TestRestoreRoute:
    async def test_success_returns_202(self, client: AsyncClient) -> None:
        with patch.object(Experiment, "restore", AsyncMock(return_value="attempt-2")):
            response = await client.post("/dash/api/experiments/abcde/restore")

        assert response.status_code == 202
        assert response.json()["attempt_id"] == "attempt-2"


class TestArchiveStatusRoute:
    async def test_returns_status_doc(self, client: AsyncClient) -> None:
        status = {
            "experiment_id": "abcde",
            "archive_state": "archiving",
            "attempt_id": "a1",
            "direction": "archive",
            "reason": None,
        }
        with patch.object(Experiment, "get_archive_status", AsyncMock(return_value=status)):
            response = await client.get("/dash/api/experiments/abcde/archive/status")

        assert response.status_code == 200
        body = response.json()
        assert body["archive_state"] == "archiving"
        assert body["attempt_id"] == "a1"
