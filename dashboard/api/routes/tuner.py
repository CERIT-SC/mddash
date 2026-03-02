from http import HTTPStatus

from api_response import ApiResponse
from config import API_PREFIX, DATA_DIR
from decorators import handle_exceptions
from extensions import db
from flask import Blueprint, Response, request
from models import Experiment, TunerJob
from schemas import TunerJobSchema
from validators import check_path

tuner_bp = Blueprint("tuner", __name__, url_prefix=f"{API_PREFIX}/experiments/<experiment_id>/tuner")


@tuner_bp.route("", methods=["GET"])
@handle_exceptions()
def list_tuner_jobs(experiment_id: str) -> Response:
    """
    List all tuner jobs for an experiment.

    Returns:
        Response: JSON response with the list of tuner jobs.
    """
    schema = TunerJobSchema(many=True)
    tuner_jobs = TunerJob.query.filter_by(experiment_id=experiment_id).all()
    return ApiResponse.success(schema.dump(tuner_jobs))


@tuner_bp.route("/<path:tpr_name>", methods=["GET"])
@handle_exceptions()
def get_tuner_job(experiment_id: str, tpr_name: str) -> Response:
    """
    Get a specific tuner job by TPR name.

    Returns:
        Response: JSON response with the tuner job data.
    """
    schema = TunerJobSchema()
    tuner_job: TunerJob = TunerJob.query.filter_by(experiment_id=experiment_id, tpr_name=tpr_name).first_or_404(
        description=f"Tuner job for {tpr_name} not found"
    )
    return ApiResponse.success(schema.dump(tuner_job))


@tuner_bp.route("/<path:tpr_name>", methods=["POST"])
@handle_exceptions(rollback=True)
def start_tuner_job(experiment_id: str, tpr_name: str) -> Response:
    """
    Start a tuner job to optimize simulation parameters.

    Returns:
        Response: JSON response with the created or existing tuner job, or an error if the TPR file does not exist.
    """
    check_path(tpr_name, DATA_DIR / experiment_id)
    schema = TunerJobSchema()
    experiment: Experiment = Experiment.query.get_or_404(
        experiment_id, description=f"Experiment {experiment_id} not found"
    )
    tuner_job: TunerJob | None = TunerJob.query.filter_by(experiment_id=experiment_id, tpr_name=tpr_name).first()
    tpr_path = DATA_DIR / experiment_id / tpr_name

    if not tpr_path.is_file():
        return ApiResponse.error(f"TPR file {tpr_name} does not exist.", HTTPStatus.NOT_FOUND)

    if tuner_job:
        if tuner_job.error_message:
            tuner_job.delete()
            db.session.delete(tuner_job)
            db.session.commit()
        else:
            return ApiResponse.success(schema.dump(tuner_job), HTTPStatus.OK)

    # Get parameters from request
    nsteps = request.args.get("nsteps", default=25000, type=int)
    extra_args = request.args.get("extra_args", default="", type=str)
    tuner_job = TunerJob.start(experiment, tpr_path, nsteps=nsteps, extra_args=extra_args)

    return ApiResponse.success(schema.dump(tuner_job), HTTPStatus.CREATED)


@tuner_bp.route("/<path:tpr_name>/stop", methods=["POST"])
@handle_exceptions(rollback=True)
def stop_tuner_job(experiment_id: str, tpr_name: str) -> Response:
    """
    Stop a running tuner job.

    Returns:
        Response: Empty JSON response with 204 No Content on success.
    """
    tuner_job: TunerJob = TunerJob.query.filter_by(experiment_id=experiment_id, tpr_name=tpr_name).first_or_404(
        description=f"Tuner job for {tpr_name} not found"
    )
    tuner_job.stop()
    db.session.commit()
    return ApiResponse.success(status=HTTPStatus.NO_CONTENT)


@tuner_bp.route("/<path:tpr_name>", methods=["DELETE"])
@handle_exceptions(rollback=True)
def delete_tuner_job(experiment_id: str, tpr_name: str) -> Response:
    """
    Delete a tuner job and its associated resources.

    Returns:
        Response: Empty JSON response with 204 No Content on success.
    """
    tuner_job: TunerJob = TunerJob.query.filter_by(experiment_id=experiment_id, tpr_name=tpr_name).first_or_404(
        description=f"Tuner job for {tpr_name} not found"
    )
    tuner_job.delete()
    db.session.delete(tuner_job)
    db.session.commit()
    return ApiResponse.success(status=HTTPStatus.NO_CONTENT)
