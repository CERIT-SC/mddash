import logging
from http import HTTPStatus
from typing import Any, cast
from uuid import uuid4

import k8s_client
from config import API_PREFIX, NAMESPACE
from decorators import handle_exceptions
from enums import AmberBinary, DeviceType, EwaldPreset
from extensions import db
from flask import Blueprint, Response, jsonify, request
from flask.typing import ResponseReturnValue
from marshmallow import ValidationError
from models import MdrunJob
from sanitization import (
    sanitize_bucket_name,
    sanitize_experiment_id,
    sanitize_extra_args,
    sanitize_inpcrd_name,
    sanitize_mdin_name,
    sanitize_prmtop_name,
    sanitize_tpr_name,
)
from schemas import AmberJobCreateRequestSchema, GmxJobCreateRequestSchema

logger = logging.getLogger(__name__)

health_bp = Blueprint("health", __name__, url_prefix=f"{API_PREFIX}")
gmx_bp = Blueprint("gmx", __name__, url_prefix=f"{API_PREFIX}/jobs/gmx")
amber_bp = Blueprint("amber", __name__, url_prefix=f"{API_PREFIX}/jobs/amber")


# Shared handlers for job operations (not routes)
def _get_job(job_id: str) -> Response:
    """
    Get the status of a specific job.

    Returns:
        Response: A JSON response containing the job ID and current status.
    """
    job: MdrunJob = MdrunJob.query.get_or_404(job_id, description=f"Job {job_id} not found")

    status_data = {"id": job.id, "status": job.status.value}

    return jsonify(status_data)


def _delete_job(job_id: str) -> ResponseReturnValue:
    """
    Delete a job and its associated Kubernetes resources.

    Returns:
        Response: An empty JSON success response with HTTP 204.
    """
    job: MdrunJob = MdrunJob.query.get_or_404(job_id, description=f"Job {job_id} not found")

    job.delete()
    db.session.delete(job)
    db.session.commit()

    return "", HTTPStatus.NO_CONTENT


# Health endpoints
@health_bp.route("", methods=["GET"])
@health_bp.route("/health", methods=["GET"])
def health_check() -> Response:
    """
    Return API health status.

    Returns:
        Response: A JSON success response indicating the API is healthy.
    """
    return jsonify("MDRun API is healthy")


# GROMACS routes
@gmx_bp.route("/<job_id>", methods=["GET"])
@handle_exceptions()
def get_gmx_job(job_id: str) -> Response:
    """
    Get GROMACS job status.

    Returns:
        JSON response with job ID and status.
    """
    return _get_job(job_id)


@gmx_bp.route("", methods=["POST"])
@handle_exceptions(rollback=True)
def create_gmx_job() -> ResponseReturnValue:
    """
    Create and start a new GROMACS simulation job.

    Returns:
        Response: A JSON response with the new job ID and status, with HTTP 201.

    Raises:
        ValidationError: If any input field fails validation or sanitization.
    """
    request_schema = GmxJobCreateRequestSchema()
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

    job_id = str(uuid4())
    job_name = f"mdrun-{job_id}"
    deffnm = tpr_name.removesuffix(".tpr")

    k8s_client.create_gromacs_job(
        ns=NAMESPACE,
        bucket_name=bucket_name,
        name=job_name,
        experiment_id=experiment_id,
        deffnm=deffnm,
        nb=nb.value,
        pme=pme.value,
        np=np,
        ntomp=ntomp,
        extra_args=extra_args,
    )

    job = MdrunJob.create(job_id=job_id, job_name=job_name, experiment_id=experiment_id)
    logger.info(f"Started GROMACS job {job_name} with ID {job_id} in experiment {experiment_id}")

    return jsonify({"id": job.id, "status": job.last_status.value}), HTTPStatus.CREATED


@gmx_bp.route("/<job_id>", methods=["DELETE"])
@handle_exceptions(rollback=True)
def delete_gmx_job(job_id: str) -> ResponseReturnValue:
    """
    Delete a GROMACS job.

    Returns:
        Empty success response with HTTP 204.
    """
    return _delete_job(job_id)


# AMBER routes
@amber_bp.route("/<job_id>", methods=["GET"])
@handle_exceptions()
def get_amber_job(job_id: str) -> Response:
    """
    Get AMBER job status.

    Returns:
        JSON response with job ID and status.
    """
    return _get_job(job_id)


@amber_bp.route("", methods=["POST"])
@handle_exceptions(rollback=True)
def create_amber_job() -> ResponseReturnValue:
    """
    Create and start a new AMBER simulation job.

    Returns:
        Response: A JSON response with the new job ID and status, with HTTP 201.

    Raises:
        ValidationError: If any input field fails validation or sanitization.
    """
    request_schema = AmberJobCreateRequestSchema()
    data = cast("dict[str, Any]", request_schema.load(request.json or {}))

    experiment_id = sanitize_experiment_id(cast("str", data.get("experiment_id")))
    prmtop_name = sanitize_prmtop_name(cast("str", data.get("prmtop_name")))
    inpcrd_name = sanitize_inpcrd_name(cast("str", data.get("inpcrd_name")))
    mdin_name = sanitize_mdin_name(cast("str", data.get("mdin_name")))
    bucket_name = sanitize_bucket_name(cast("str", data.get("bucket_name")))
    extra_args = sanitize_extra_args(cast("str", data.get("extra_args", "")))

    np = int(data["np"])
    ntomp = int(data["ntomp"])
    if np <= 0 or ntomp <= 0:
        raise ValidationError("np and ntomp must be positive integers.")

    try:
        binary = AmberBinary.from_string(cast("str", data["binary"]))
        ewald = EwaldPreset.from_string(cast("str", data["ewald"]))
    except ValueError as e:
        raise ValidationError(str(e)) from e

    job_id = str(uuid4())
    job_name = f"mdrun-{job_id}"

    k8s_client.create_amber_job(
        ns=NAMESPACE,
        bucket_name=bucket_name,
        name=job_name,
        experiment_id=experiment_id,
        prmtop_name=prmtop_name,
        inpcrd_name=inpcrd_name,
        mdin_name=mdin_name,
        binary=binary.value,
        np=np,
        ntomp=ntomp,
        ewald=ewald.value,
        extra_args=extra_args,
    )

    job = MdrunJob.create(job_id=job_id, job_name=job_name, experiment_id=experiment_id)
    logger.info(f"Started AMBER job {job_name} with ID {job_id} in experiment {experiment_id}")

    return jsonify({"id": job.id, "status": job.last_status.value}), HTTPStatus.CREATED


@amber_bp.route("/<job_id>", methods=["DELETE"])
@handle_exceptions(rollback=True)
def delete_amber_job(job_id: str) -> ResponseReturnValue:
    """
    Delete an AMBER job.

    Returns:
        Empty success response with HTTP 204.
    """
    return _delete_job(job_id)
