from io import BytesIO
from unittest.mock import MagicMock, patch

from api.main import app
from fastapi.testclient import TestClient

client = TestClient(app, raise_server_exceptions=True)
AUTH = ("test-user", "test-password")


def _fake_tpr() -> BytesIO:
    return BytesIO(b"fake tpr content")


class TestCreateGmxTuningJob:
    @patch("api.routers.gmx.submit_tuning_job")
    def test_returns_job_id(self, mock_submit) -> None:
        mock_submit.return_value = "test-job-id"
        response = client.post(
            "/api/tuning-jobs/gmx",
            auth=AUTH,
            files={"file": ("md.tpr", _fake_tpr(), "application/octet-stream")},
            data={"nsteps": "1000"},
        )
        assert response.status_code == 201
        assert "id" in response.json()

    def test_rejects_wrong_extension(self) -> None:
        response = client.post(
            "/api/tuning-jobs/gmx",
            auth=AUTH,
            files={"file": ("md.txt", BytesIO(b"bad"), "text/plain")},
        )
        assert response.status_code == 400

    def test_requires_auth(self) -> None:
        response = client.post(
            "/api/tuning-jobs/gmx",
            files={"file": ("md.tpr", _fake_tpr(), "application/octet-stream")},
        )
        assert response.status_code == 401


class TestGetGmxStatus:
    @patch("api.routers.gmx.get_job")
    @patch("api.routers.gmx.sync_job_status")
    @patch("api.routers.gmx.get_trials_by_job_id")
    def test_returns_status(self, mock_trials, mock_sync, mock_get_job) -> None:
        job = MagicMock()
        job.status = "RUNNING"
        job.engine = "gmx"
        job.error = None
        mock_get_job.return_value = job
        mock_trials.return_value = []

        response = client.get("/api/tuning-jobs/gmx/test-id/status", auth=AUTH)
        assert response.status_code == 200
        assert response.json()["status"] == "RUNNING"

    @patch("api.routers.gmx.get_job")
    def test_returns_404_for_missing_job(self, mock_get_job) -> None:
        mock_get_job.return_value = None
        response = client.get("/api/tuning-jobs/gmx/nonexistent/status", auth=AUTH)
        assert response.status_code == 404

    @patch("api.routers.gmx.get_job")
    def test_returns_404_for_wrong_engine(self, mock_get_job) -> None:
        job = MagicMock()
        job.engine = "amber"
        mock_get_job.return_value = job
        response = client.get("/api/tuning-jobs/gmx/some-amber-job/status", auth=AUTH)
        assert response.status_code == 404


class TestDeleteGmxTuningJob:
    @patch("api.routers._shared.get_job")
    @patch("api.routers._shared.cancel_job")
    @patch("api.routers._shared.delete_job")
    @patch("api.routers._shared.cleanup_job_files")
    def test_deletes_job(self, mock_cleanup, mock_delete, mock_cancel, mock_get_job) -> None:
        job = MagicMock()
        job.engine = "gmx"
        mock_get_job.return_value = job
        mock_cancel.return_value = True
        response = client.delete("/api/tuning-jobs/gmx/test-id", auth=AUTH)
        assert response.status_code == 204

    @patch("api.routers._shared.get_job")
    def test_returns_404_for_amber_job(self, mock_get_job) -> None:
        job = MagicMock()
        job.engine = "amber"
        mock_get_job.return_value = job

        response = client.delete("/api/tuning-jobs/gmx/test-id", auth=AUTH)

        assert response.status_code == 404
