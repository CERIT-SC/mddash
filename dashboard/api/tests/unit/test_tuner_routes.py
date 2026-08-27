"""Unit tests for the tuner start route's nsteps validation."""

import uuid
from http import HTTPStatus

import pytest
from extensions import db
from flask import Flask
from flask.testing import FlaskClient


@pytest.fixture
def experiment_id(app: Flask) -> str:
    """Seed a minimal experiment for the tuner route."""
    from models import Experiment

    with app.app_context():
        exp = Experiment(id="tunr1", name="Tuner Route", notebooks_repo="https://github.com/t/r.git")
        db.session.add(exp)
        db.session.commit()
        return exp.id


class TestTunerNstepsValidation:
    """nsteps is caller-supplied and must be a positive integer — bad values are 400, never 500."""

    URL = "/dash/api/experiments/tunr1/tuner"

    def test_missing_nsteps_is_400(self, client: FlaskClient, experiment_id: str) -> None:
        response = client.post(self.URL, json={"simulation_path": "prod/test.simulation.json"})
        assert response.status_code == HTTPStatus.BAD_REQUEST
        assert "nsteps" in response.get_json()["detail"]

    @pytest.mark.parametrize("nsteps", ["abc", [1], {"n": 1}, 0, -5])
    def test_invalid_nsteps_is_400(self, client: FlaskClient, experiment_id: str, nsteps: object) -> None:
        """Non-integer and non-positive values are rejected."""
        response = client.post(self.URL, json={"simulation_path": "prod/test.simulation.json", "nsteps": nsteps})
        assert response.status_code == HTTPStatus.BAD_REQUEST

    def test_valid_nsteps_reaches_tuner_job_start(
        self, client: FlaskClient, experiment_id: str, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from models.tuner_job import TunerJob

        captured: dict[str, int] = {}

        def fake_start(cls: type, experiment: object, simulation_path: str, nsteps: int) -> TunerJob:
            captured["nsteps"] = nsteps
            return TunerJob(
                id=str(uuid.uuid4()),
                experiment_id=experiment_id,
                simulation_path=simulation_path,
                nsteps=nsteps,
            )

        monkeypatch.setattr(TunerJob, "start", classmethod(fake_start))

        response = client.post(self.URL, json={"simulation_path": "prod/test.simulation.json", "nsteps": "1000"})
        assert response.status_code == HTTPStatus.CREATED
        assert captured["nsteps"] == 1000
