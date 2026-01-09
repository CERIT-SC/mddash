"""
Integration tests for mdrun-api routes.

Tests the full request/response cycle with mocked Kubernetes.
"""

import json
from http import HTTPStatus
from typing import Any

from flask.testing import FlaskClient
from sqlalchemy.orm import Session


class TestHealthEndpoint:
    """Tests for health check endpoints."""

    def test_health_root_returns_ok(self, client: FlaskClient) -> None:
        """Root API endpoint should return health status."""
        response = client.get("/api")

        assert response.status_code == HTTPStatus.OK

    def test_health_endpoint_returns_ok(self, client: FlaskClient) -> None:
        """Health endpoint should return 200 OK."""
        response = client.get("/api/health")

        assert response.status_code == HTTPStatus.OK
        data = json.loads(response.data)
        assert data["success"] is True


class TestGetJob:
    """Tests for GET /api/jobs/<job_id>."""

    def test_returns_404_for_missing_job(self, client: FlaskClient) -> None:
        """Should return 404 for non-existent job ID."""
        response = client.get("/api/jobs/nonexistent-id")

        assert response.status_code == HTTPStatus.NOT_FOUND

    def test_returns_job_status(
        self, client: FlaskClient, db_session: Session, mock_k8s_client: dict[str, Any]
    ) -> None:
        """Should return job status for existing job."""
        from enums import JobStatus
        from models import MdrunJob

        # Create test job directly in DB
        job = MdrunJob()
        job.id = "test-job-123"
        job.job_name = "mdrun-test-job-123"
        job.experiment_id = "exp123"
        job.last_status = JobStatus.RUNNING
        db_session.add(job)
        db_session.commit()

        # Mock K8s status check
        mock_k8s_client["get_job_status"].return_value = JobStatus.RUNNING

        response = client.get("/api/jobs/test-job-123")

        assert response.status_code == HTTPStatus.OK
        data = json.loads(response.data)
        assert data["data"]["id"] == "test-job-123"
        assert data["data"]["status"] == "running"


class TestCreateJob:
    """Tests for POST /api/jobs."""

    def test_create_job_success(self, client: FlaskClient, mock_k8s_client: dict[str, Any]) -> None:
        """Should create job and return 201."""
        response = client.post(
            "/api/jobs",
            json={
                "experiment_id": "exp123",
                "tpr_name": "simulation.tpr",
                "bucket_name": "test-bucket",
                "pme": "auto",
                "nb": "auto",
                "np": 1,
                "ntomp": 4,
            },
            content_type="application/json",
        )

        assert response.status_code == HTTPStatus.CREATED
        data = json.loads(response.data)
        assert data["success"] is True
        assert "id" in data["data"]
        assert data["data"]["status"] == "pending"

        # Verify K8s job was created
        mock_k8s_client["create_gromacs_job"].assert_called_once()

    def test_create_job_with_extra_args(self, client: FlaskClient, mock_k8s_client: dict[str, Any]) -> None:
        """Should pass extra_args to job creation."""
        response = client.post(
            "/api/jobs",
            json={
                "experiment_id": "exp456",
                "tpr_name": "run.tpr",
                "bucket_name": "bucket",
                "pme": "gpu",
                "nb": "gpu",
                "np": 2,
                "ntomp": 8,
                "extra_args": "-nsteps 1000",
            },
            content_type="application/json",
        )

        assert response.status_code == HTTPStatus.CREATED

        # Verify extra_args was passed
        call_kwargs = mock_k8s_client["create_gromacs_job"].call_args.kwargs
        assert call_kwargs["extra_args"] == "-nsteps 1000"

    def test_create_job_missing_required_fields(self, client: FlaskClient) -> None:
        """Should return error for missing required fields."""
        response = client.post(
            "/api/jobs",
            json={"experiment_id": "exp123"},
            content_type="application/json",
        )

        # API returns 500 because decorator catches validation error
        assert response.status_code == HTTPStatus.INTERNAL_SERVER_ERROR
        data = json.loads(response.data)
        assert data["success"] is False


class TestDeleteJob:
    """Tests for DELETE /api/jobs/<job_id>."""

    def test_delete_existing_job(
        self, client: FlaskClient, db_session: Session, mock_k8s_client: dict[str, Any]
    ) -> None:
        """Should delete job and return 204."""
        from enums import JobStatus
        from models import MdrunJob

        # Create test job
        job = MdrunJob()
        job.id = "delete-me"
        job.job_name = "mdrun-delete-me"
        job.experiment_id = "exp123"
        job.last_status = JobStatus.TERMINATED
        db_session.add(job)
        db_session.commit()

        response = client.delete("/api/jobs/delete-me")

        assert response.status_code == HTTPStatus.NO_CONTENT

        # Verify K8s job was deleted
        mock_k8s_client["delete_job"].assert_called_once()

    def test_delete_nonexistent_job(self, client: FlaskClient) -> None:
        """Should return 404 for non-existent job."""
        response = client.delete("/api/jobs/not-found")

        assert response.status_code == HTTPStatus.NOT_FOUND
