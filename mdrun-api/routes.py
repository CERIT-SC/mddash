import logging
from http import HTTPStatus
from typing import Any, cast

from api_response import ApiResponse
from config import API_PREFIX
from decorators import handle_exceptions
from enums import DeviceType
from extensions import db
from flask import Blueprint, Response, request
from marshmallow import ValidationError
from models import MdrunJob
from sanitization import sanitize_bucket_name, sanitize_experiment_id, sanitize_extra_args, sanitize_tpr_name
from schemas import JobCreateRequestSchema

logger = logging.getLogger(__name__)

health_bp = Blueprint("health", __name__, url_prefix=f"{API_PREFIX}")
mdrun_bp = Blueprint("mdrun", __name__, url_prefix=f"{API_PREFIX}/jobs")


@health_bp.route("", methods=["GET"])
@health_bp.route("/health", methods=["GET"])
def health_check() -> Response:
    """
    Return API health status.

    Returns:
        Response: A JSON success response indicating the API is healthy.
    """
    return ApiResponse.success("MDRun API is healthy", HTTPStatus.OK)


@mdrun_bp.route("/<job_id>", methods=["GET"])
@handle_exceptions()
def get_job(job_id: str) -> Response:
    """
    Get the status of a specific job.

    Returns:
        Response: A JSON response containing the job ID and current status.
    """
    job: MdrunJob = MdrunJob.query.get_or_404(job_id, description=f"Job {job_id} not found")

    status_data = {"id": job.id, "status": job.status.value}

    return ApiResponse.success(status_data)


@mdrun_bp.route("", methods=["POST"])
@handle_exceptions(rollback=True)
def create_job() -> Response:
    """
    Create and start a new GROMACS simulation job.

    Returns:
        Response: A JSON response with the new job ID and status, with HTTP 201.

    Raises:
        ValidationError: If any input field fails validation or sanitization.
    """
    request_schema = JobCreateRequestSchema()
    data = cast("dict[str, Any]", request_schema.load(request.json or {}))

    experiment_id = sanitize_experiment_id(cast("str", data.get("experiment_id")))
    tpr_name = sanitize_tpr_name(cast("str", data.get("tpr_name")))
    bucket_name = sanitize_bucket_name(cast("str", data.get("bucket_name")))
    extra_args = sanitize_extra_args(cast("str", data.get("extra_args", "")))

    np = int(data["np"])
    ntomp = int(data["ntomp"])
    if np <= 0 or ntomp <= 0:
        raise ValidationError("np and ntomp must be positive integers.")

    try:
        pme = DeviceType.from_string(cast("str", data["pme"]))
        nb = DeviceType.from_string(cast("str", data["nb"]))
    except ValueError as e:
        raise ValidationError(str(e)) from e

    job: MdrunJob = MdrunJob.create_and_start(
        experiment_id=experiment_id,
        tpr_name=tpr_name,
        bucket_name=bucket_name,
        pme=pme,
        nb=nb,
        np=np,
        ntomp=ntomp,
        extra_args=extra_args,
    )

    return ApiResponse.success({"id": job.id, "status": job.last_status.value}, HTTPStatus.CREATED)


@mdrun_bp.route("/<job_id>", methods=["DELETE"])
@handle_exceptions(rollback=True)
def delete_job(job_id: str) -> Response:
    """
    Delete a job and its associated Kubernetes resources.

    Returns:
        Response: An empty JSON success response with HTTP 204.
    """
    job: MdrunJob = MdrunJob.query.get_or_404(job_id, description=f"Job {job_id} not found")

    db.session.delete(job)
    db.session.commit()
    job.delete()

    return ApiResponse.success(status=HTTPStatus.NO_CONTENT)
