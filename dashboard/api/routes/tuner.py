from http import HTTPStatus

from api_response import ApiResponse
from config import API_PREFIX, DATA_DIR
from decorators import handle_exceptions
from extensions import db
from flask import Blueprint, Response, request
from models import Experiment, TunerJob
from schemas import TunerJobSchema
from utils import check_filename

tuner_bp = Blueprint("tuner", __name__, url_prefix=f"{API_PREFIX}/experiments/<experiment_id>/tuner")


@tuner_bp.route("", methods=["GET"])
@handle_exceptions()
def list_tuner_jobs(experiment_id: str) -> Response:
    """List all tuner jobs for an experiment."""
    schema = TunerJobSchema(many=True)
    tuner_jobs = TunerJob.query.filter_by(experiment_id=experiment_id).all()
    return ApiResponse.success(schema.dump(tuner_jobs))


@tuner_bp.route("/<tpr_name>", methods=["GET"])
@handle_exceptions()
def get_tuner_job(experiment_id: str, tpr_name: str) -> Response:
    """Get a specific tuner job by TPR name."""
    schema = TunerJobSchema()
    tuner_job: TunerJob = TunerJob.query.filter_by(experiment_id=experiment_id, tpr_name=tpr_name).first_or_404(
        description=f"Tuner job for {tpr_name} not found"
    )
    return ApiResponse.success(schema.dump(tuner_job))


@tuner_bp.route("/<tpr_name>", methods=["POST"])
@handle_exceptions(rollback=True)
def start_tuner_job(experiment_id: str, tpr_name: str) -> Response:
    """Start a tuner job to optimize simulation parameters."""
    check_filename(tpr_name, allowed_extensions=["tpr"])
    schema = TunerJobSchema()
    experiment: Experiment = Experiment.query.get_or_404(
        experiment_id, description=f"Experiment {experiment_id} not found"
    )
    tuner_job = TunerJob.query.filter_by(experiment_id=experiment_id, tpr_name=tpr_name).first()
    tpr_path = DATA_DIR / experiment_id / tpr_name

    if not tpr_path.exists():
        return ApiResponse.error(f"TPR file {tpr_name} does not exist.", HTTPStatus.NOT_FOUND)

    if tuner_job:
        # Job already exists
        return ApiResponse.success(schema.dump(tuner_job), HTTPStatus.OK)

    # Get nsteps from query parameter, default to 25000 (50 ps)
    nsteps = request.args.get("nsteps", default=25000, type=int)
    tuner_job = TunerJob.start(experiment, tpr_path, nsteps=nsteps)

    return ApiResponse.success(schema.dump(tuner_job), HTTPStatus.CREATED)


@tuner_bp.route("/<tpr_name>/stop", methods=["POST"])
@handle_exceptions(rollback=True)
def stop_tuner_job(experiment_id: str, tpr_name: str) -> Response:
    """Stop a running tuner job."""
    tuner_job: TunerJob = TunerJob.query.filter_by(experiment_id=experiment_id, tpr_name=tpr_name).first_or_404(
        description=f"Tuner job for {tpr_name} not found"
    )
    tuner_job.stop()
    db.session.commit()
    return ApiResponse.success(status=HTTPStatus.NO_CONTENT)


@tuner_bp.route("/<tpr_name>", methods=["DELETE"])
@handle_exceptions(rollback=True)
def delete_tuner_job(experiment_id: str, tpr_name: str) -> Response:
    """Delete a tuner job and its associated resources."""
    tuner_job: TunerJob = TunerJob.query.filter_by(experiment_id=experiment_id, tpr_name=tpr_name).first_or_404(
        description=f"Tuner job for {tpr_name} not found"
    )
    tuner_job.delete()
    db.session.delete(tuner_job)
    db.session.commit()
    return ApiResponse.success(status=HTTPStatus.NO_CONTENT)
