from io import BytesIO
from unittest.mock import MagicMock, patch

from api.main import app
from fastapi.testclient import TestClient

client = TestClient(app, raise_server_exceptions=True)
AUTH = ("test-user", "test-password")


def _fake_prmtop() -> BytesIO:
    return BytesIO(b"fake prmtop content")


def _fake_inpcrd() -> BytesIO:
    return BytesIO(b"fake inpcrd content")


def _fake_mdin() -> BytesIO:
    return BytesIO(b" &cntrl\n  nstlim = 10000,\n /\n")


class TestCreateAmberTuningJob:
    @patch("api.routers.amber.submit_tuning_job")
    def test_returns_job_id(self, mock_submit) -> None:
        mock_submit.return_value = "test-amber-job"
        response = client.post(
            "/api/tuning-jobs/amber",
            auth=AUTH,
            files={
                "prmtop": ("system.prmtop", _fake_prmtop(), "application/octet-stream"),
                "inpcrd": ("system.inpcrd", _fake_inpcrd(), "application/octet-stream"),
                "mdin": ("md.mdin", _fake_mdin(), "text/plain"),
            },
            data={"nsteps": "5000"},
        )
        assert response.status_code == 201
        assert "id" in response.json()

    def test_rejects_wrong_prmtop_extension(self) -> None:
        response = client.post(
            "/api/tuning-jobs/amber",
            auth=AUTH,
            files={
                "prmtop": ("system.txt", _fake_prmtop(), "application/octet-stream"),
                "inpcrd": ("system.inpcrd", _fake_inpcrd(), "application/octet-stream"),
                "mdin": ("md.mdin", _fake_mdin(), "text/plain"),
            },
        )
        assert response.status_code in {400, 401}

    def test_requires_auth(self) -> None:
        response = client.post(
            "/api/tuning-jobs/amber",
            files={
                "prmtop": ("system.prmtop", _fake_prmtop(), "application/octet-stream"),
                "inpcrd": ("system.inpcrd", _fake_inpcrd(), "application/octet-stream"),
                "mdin": ("md.mdin", _fake_mdin(), "text/plain"),
            },
        )
        assert response.status_code == 401


class TestGetAmberStatus:
    @patch("api.routers.amber.get_job")
    @patch("api.routers.amber.sync_job_status")
    @patch("api.routers.amber.get_trials_by_job_id")
    def test_returns_status(self, mock_trials, mock_sync, mock_get_job) -> None:
        job = MagicMock()
        job.status = "RUNNING"
        job.engine = "amber"
        job.error = None
        mock_get_job.return_value = job
        mock_trials.return_value = []

        response = client.get("/api/tuning-jobs/amber/test-id/status", auth=AUTH)
        assert response.status_code == 200

    @patch("api.routers.amber.get_job")
    def test_returns_404_for_wrong_engine(self, mock_get_job) -> None:
        job = MagicMock()
        job.engine = "gmx"
        mock_get_job.return_value = job
        response = client.get("/api/tuning-jobs/amber/some-gmx-job/status", auth=AUTH)
        assert response.status_code == 404
