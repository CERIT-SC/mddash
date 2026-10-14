"""Unit tests for the tuner start route's nsteps validation."""

import uuid
from datetime import UTC, datetime
from http import HTTPStatus

import pytest
from httpx import AsyncClient
from models import Experiment, Notebook
from sqlalchemy.ext.asyncio import AsyncSession


@pytest.fixture
async def experiment_id(db_session: AsyncSession) -> str:
    """Seed a minimal experiment for the tuner route."""
    db_session.add(Experiment(id="tunr1", name="Tuner Route", notebooks_repo="https://github.com/t/r.git"))
    db_session.add(Notebook(experiment_id="tunr1"))
    await db_session.commit()
    return "tunr1"


class TestTunerNstepsValidation:
    """nsteps is caller-supplied and must be a positive integer — bad values are 400, never 500."""

    URL = "/dash/api/experiments/tunr1/tuner"

    async def test_missing_nsteps_is_400(self, client: AsyncClient, experiment_id: str) -> None:
        response = await client.post(self.URL, json={"simulation_path": "prod/test.simulation.json"})
        assert response.status_code == HTTPStatus.BAD_REQUEST
        assert "nsteps" in response.json()["detail"]

    @pytest.mark.parametrize("nsteps", ["abc", [1], {"n": 1}, 0, -5])
    async def test_invalid_nsteps_is_400(self, client: AsyncClient, experiment_id: str, nsteps: object) -> None:
        """Non-integer and non-positive values are rejected."""
        response = await client.post(self.URL, json={"simulation_path": "prod/test.simulation.json", "nsteps": nsteps})
        assert response.status_code == HTTPStatus.BAD_REQUEST

    async def test_valid_nsteps_reaches_tuner_job_start(
        self, client: AsyncClient, experiment_id: str, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from models.tuner_job import TunerJob

        captured: dict[str, int] = {}

        async def fake_start(  # ruff:ignore[unused-async]
            cls: type, session: AsyncSession, experiment: Experiment, simulation_path: str, nsteps: int
        ) -> TunerJob:
            captured["nsteps"] = nsteps
            # A stopped job skips the tuner poll the route performs before serializing.
            return TunerJob(
                id=str(uuid.uuid4()),
                experiment=experiment,
                experiment_id=experiment.id,
                simulation_path=simulation_path,
                nsteps=nsteps,
                is_stopped=True,
                created_at=datetime.now(UTC),
            )

        monkeypatch.setattr(TunerJob, "start", classmethod(fake_start))

        response = await client.post(self.URL, json={"simulation_path": "prod/test.simulation.json", "nsteps": "1000"})
        assert response.status_code == HTTPStatus.CREATED
        assert captured["nsteps"] == 1000
        assert response.json()["nsteps"] == 1000
