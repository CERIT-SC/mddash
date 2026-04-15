"""
Integration tests for mdrun-api routes.

Tests the full request/response cycle with mocked Kubernetes.
"""

import json
from http import HTTPStatus
from typing import Any

from enums import JobStatus
from flask.testing import FlaskClient
from models import MdrunJob
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


class TestGetGmxJob:
    """Tests for GET /api/jobs/gmx/<job_id>."""

    def test_returns_404_for_missing_job(self, client: FlaskClient) -> None:
        """Should return 404 for non-existent job ID."""
        response = client.get("/api/jobs/gmx/nonexistent-id")

        assert response.status_code == HTTPStatus.NOT_FOUND

    def test_returns_job_status(
        self, client: FlaskClient, db_session: Session, mock_k8s_client: dict[str, Any]
    ) -> None:
        """Should return job status for existing job."""
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

        response = client.get("/api/jobs/gmx/test-job-123")

        assert response.status_code == HTTPStatus.OK
        data = json.loads(response.data)
        assert data["data"]["id"] == "test-job-123"
        assert data["data"]["status"] == "running"


class TestCreateGmxJob:
    """Tests for POST /api/jobs/gmx."""

    def test_create_job_success(self, client: FlaskClient, mock_k8s_client: dict[str, Any]) -> None:
        """Should create job and return 201."""
        response = client.post(
            "/api/jobs/gmx",
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
            "/api/jobs/gmx",
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
            "/api/jobs/gmx",
            json={"experiment_id": "exp123"},
            content_type="application/json",
        )

        assert response.status_code == HTTPStatus.BAD_REQUEST
        data = json.loads(response.data)
        assert data["success"] is False


class TestDeleteGmxJob:
    """Tests for DELETE /api/jobs/gmx/<job_id>."""

    def test_delete_existing_job(
        self, client: FlaskClient, db_session: Session, mock_k8s_client: dict[str, Any]
    ) -> None:
        """Should delete job and return 204."""
        # Create test job
        job = MdrunJob()
        job.id = "delete-me"
        job.job_name = "mdrun-delete-me"
        job.experiment_id = "exp123"
        job.last_status = JobStatus.TERMINATED
        db_session.add(job)
        db_session.commit()

        response = client.delete("/api/jobs/gmx/delete-me")

        assert response.status_code == HTTPStatus.NO_CONTENT

        # Verify K8s job was deleted
        mock_k8s_client["delete_job"].assert_called_once()

    def test_delete_nonexistent_job(self, client: FlaskClient) -> None:
        """Should return 404 for non-existent job."""
        response = client.delete("/api/jobs/gmx/not-found")

        assert response.status_code == HTTPStatus.NOT_FOUND


class TestGetAmberJob:
    """Tests for GET /api/jobs/amber/<job_id>."""

    def test_returns_404_for_missing_job(self, client: FlaskClient) -> None:
        """Should return 404 for non-existent job ID."""
        response = client.get("/api/jobs/amber/nonexistent-id")

        assert response.status_code == HTTPStatus.NOT_FOUND


class TestCreateAmberJob:
    """Tests for POST /api/jobs/amber."""

    def test_create_amber_job_success(self, client: FlaskClient, mock_k8s_client: dict[str, Any]) -> None:
        """Should create AMBER job and return 201."""
        response = client.post(
            "/api/jobs/amber",
            json={
                "experiment_id": "exp123",
                "prmtop_name": "system.prmtop",
                "inpcrd_name": "system.rst7",
                "mdin_name": "prod.in",
                "bucket_name": "test-bucket",
                "binary": "pmemd.cuda",
                "np": 1,
                "ntomp": 4,
                "ewald": "default",
            },
            content_type="application/json",
        )

        assert response.status_code == HTTPStatus.CREATED
        data = json.loads(response.data)
        assert data["success"] is True
        assert "id" in data["data"]
        assert data["data"]["status"] == "pending"

        # Verify K8s job was created
        mock_k8s_client["create_amber_job"].assert_called_once()


class TestDeleteAmberJob:
    """Tests for DELETE /api/jobs/amber/<job_id>."""

    def test_delete_nonexistent_job(self, client: FlaskClient) -> None:
        """Should return 404 for non-existent job."""
        response = client.delete("/api/jobs/amber/not-found")

        assert response.status_code == HTTPStatus.NOT_FOUND