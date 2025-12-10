import logging
from http import HTTPStatus
from typing import Any, cast

from api_response import ApiResponse
from config import API_PREFIX
from decorators import handle_exceptions
from enums import DeviceType
from extensions import db
from flask import Blueprint, Response, request
from models import MdrunJob
from schemas import JobCreateRequestSchema

logger = logging.getLogger(__name__)

health_bp = Blueprint("health", __name__, url_prefix=f"{API_PREFIX}")
mdrun_bp = Blueprint("mdrun", __name__, url_prefix=f"{API_PREFIX}/jobs")


@health_bp.route("", methods=["GET"])
@health_bp.route("/health", methods=["GET"])
def health_check() -> Response:
    """Return API health status."""
    return ApiResponse.success("MDRun API is healthy", HTTPStatus.OK)


@mdrun_bp.route("/<job_id>", methods=["GET"])
@handle_exceptions()
def get_job(job_id: str) -> Response:
    """Get the status of a specific job."""
    job: MdrunJob = MdrunJob.query.get_or_404(job_id, description=f"Job {job_id} not found")

    status_data = {"id": job.id, "status": job.status.value}

    return ApiResponse.success(status_data)


@mdrun_bp.route("", methods=["POST"])
@handle_exceptions(rollback=True)
def create_job() -> Response:
    """Create and start a new GROMACS simulation job."""
    request_schema = JobCreateRequestSchema()
    data = cast("dict[str, Any]", request_schema.load(request.json or {}))

    job: MdrunJob = MdrunJob.create_and_start(
        experiment_id=data["experiment_id"],
        tpr_name=data["tpr_name"],
        bucket_name=data["bucket_name"],
        pme=DeviceType.from_string(data["pme"]),
        nb=DeviceType.from_string(data["nb"]),
        np=data["np"],
        ntomp=data["ntomp"],
        extra_args=data.get("extra_args", ""),
    )

    # TODO: add sanitization of user input

    return ApiResponse.success({"id": job.id, "status": job.status.value}, HTTPStatus.CREATED)


@mdrun_bp.route("/<job_id>", methods=["DELETE"])
@handle_exceptions(rollback=True)
def delete_job(job_id: str) -> Response:
    """Delete a job and its associated Kubernetes resources."""
    job: MdrunJob = MdrunJob.query.get_or_404(job_id, description=f"Job {job_id} not found")

    db.session.delete(job)
    db.session.commit()
    job.delete()

    return ApiResponse.success(status=HTTPStatus.NO_CONTENT)
