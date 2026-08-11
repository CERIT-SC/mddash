from io import BytesIO
from unittest.mock import MagicMock, patch

import pytest
from api.main import app
from api.schemas.common import JobStatus
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

    @patch("api.routers.gmx.submit_tuning_job")
    def test_nsteps_override_forwarded(self, mock_submit) -> None:
        mock_submit.return_value = "test-job-id"
        response = client.post(
            "/api/tuning-jobs/gmx",
            auth=AUTH,
            files={"file": ("md.tpr", _fake_tpr(), "application/octet-stream")},
            data={"extra_args": "-pin on -nsteps 500000"},
        )
        assert response.status_code == 201
        assert mock_submit.call_args.kwargs["extra_args"] == "-pin on"
        assert mock_submit.call_args.kwargs["nsteps_override"] == 500000

    @patch("api.routers.gmx.submit_tuning_job")
    def test_invalid_nsteps_override_rejected(self, mock_submit) -> None:
        response = client.post(
            "/api/tuning-jobs/gmx",
            auth=AUTH,
            files={"file": ("md.tpr", _fake_tpr(), "application/octet-stream")},
            data={"extra_args": "-nsteps 0"},
        )
        assert response.status_code == 400
        mock_submit.assert_not_called()


class TestGetGmxStatus:
    @patch("api.routers._shared.trial_status_overrides")
    @patch("api.routers.gmx.get_job")
    @patch("api.routers.gmx.sync_job_status")
    @patch("api.routers.gmx.get_trials_by_job_id")
    def test_no_executed_trials_reports_pending(self, mock_trials, mock_sync, mock_get_job, mock_overrides) -> None:
        job = MagicMock()
        job.status = "RUNNING"
        job.engine = "gmx"
        job.error = None
        job.sim_length_ns = 100.0
        mock_get_job.return_value = job
        mock_trials.return_value = []
        mock_overrides.return_value = {}

        response = client.get("/api/tuning-jobs/gmx/test-id/status", auth=AUTH)
        assert response.status_code == 200
        assert response.json()["status"] == "PENDING"
        assert response.json()["sim_length_ns"] == 100.0

    @patch("api.routers._shared.trial_status_overrides")
    @patch("api.routers.gmx.get_job")
    @patch("api.routers.gmx.sync_job_status")
    @patch("api.routers.gmx.get_trials_by_job_id")
    def test_queued_trial_shown_pending(self, mock_trials, mock_sync, mock_get_job, mock_overrides) -> None:
        job = MagicMock()
        job.status = "RUNNING"
        job.engine = "gmx"
        job.error = None
        job.sim_length_ns = None
        mock_get_job.return_value = job

        trial = MagicMock()
        trial.id = 5
        trial.status = "PENDING"
        trial.config_json = {"ntomp": 2, "np": 4, "nb": "gpu", "pme": "cpu"}
        trial.performance = None
        mock_trials.return_value = [trial]
        mock_overrides.return_value = {}

        response = client.get("/api/tuning-jobs/gmx/test-id/status", auth=AUTH)
        assert response.status_code == 200
        assert response.json()["status"] == "PENDING"
        [t] = response.json()["trials"]
        assert t["status"] == "PENDING"

    @patch("api.routers._shared.trial_status_overrides")
    @patch("api.routers.gmx.get_job")
    @patch("api.routers.gmx.sync_job_status")
    @patch("api.routers.gmx.get_trials_by_job_id")
    def test_ray_running_trial_shown_running(self, mock_trials, mock_sync, mock_get_job, mock_overrides) -> None:
        job = MagicMock()
        job.status = "RUNNING"
        job.engine = "gmx"
        job.error = None
        job.sim_length_ns = None
        mock_get_job.return_value = job

        trial = MagicMock()
        trial.id = 5
        trial.status = "PENDING"
        trial.config_json = {"ntomp": 2, "np": 4, "nb": "gpu", "pme": "cpu"}
        trial.performance = None
        mock_trials.return_value = [trial]
        mock_overrides.return_value = {5: JobStatus.RUNNING}

        response = client.get("/api/tuning-jobs/gmx/test-id/status", auth=AUTH)
        assert response.status_code == 200
        assert response.json()["status"] == "RUNNING"
        [t] = response.json()["trials"]
        assert t["status"] == "RUNNING"

    @patch("api.routers.gmx.get_job")
    @patch("api.routers.gmx.sync_job_status")
    @patch("api.routers.gmx.get_trials_by_job_id")
    def test_trial_estimates(self, mock_trials, mock_sync, mock_get_job) -> None:
        job = MagicMock()
        job.status = "FINISHED"
        job.engine = "gmx"
        job.error = None
        job.sim_length_ns = 100.0
        mock_get_job.return_value = job

        trial = MagicMock()
        trial.id = 5
        trial.status = "FINISHED"
        trial.config_json = {"ntomp": 2, "np": 4, "nb": "gpu", "pme": "cpu"}
        trial.performance = 100.0
        mock_trials.return_value = [trial]

        response = client.get("/api/tuning-jobs/gmx/test-id/status", auth=AUTH)
        assert response.status_code == 200
        [t] = response.json()["trials"]
        # 100 ns at 100 ns/day -> 24 hours; 8 cores * 0.04 + 1 GPU * 3.0 + 16 GB * 0.005 = 3.4/h
        assert t["estimated_time"] == 24.0
        assert t["estimated_cost"] == pytest.approx(81.6)

    @patch("api.routers.gmx.get_job")
    @patch("api.routers.gmx.sync_job_status")
    @patch("api.routers.gmx.get_trials_by_job_id")
    def test_trial_estimates_null_without_performance(self, mock_trials, mock_sync, mock_get_job) -> None:
        job = MagicMock()
        job.status = "RUNNING"
        job.engine = "gmx"
        job.error = None
        job.sim_length_ns = None
        mock_get_job.return_value = job

        trial = MagicMock()
        trial.id = 5
        trial.status = "RUNNING"
        trial.config_json = {"ntomp": 2, "np": 4, "nb": "cpu", "pme": "cpu"}
        trial.performance = None
        mock_trials.return_value = [trial]

        response = client.get("/api/tuning-jobs/gmx/test-id/status", auth=AUTH)
        assert response.status_code == 200
        [t] = response.json()["trials"]
        assert t["estimated_time"] is None
        assert t["estimated_cost"] is None

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
