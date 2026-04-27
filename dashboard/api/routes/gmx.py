from http import HTTPStatus

from config import API_PREFIX, DATA_DIR
from decorators import handle_exceptions
from enums import DeviceType
from extensions import db
from flask import Blueprint, Response, jsonify, request
from models import Experiment, GromacsJob
from schemas import GromacsJobSchema
from validators import check_log_type, check_path, check_positive_int
from werkzeug.exceptions import NotFound

gmx_bp = Blueprint("gmx", __name__, url_prefix=f"{API_PREFIX}/experiments/<experiment_id>/gmx")


@gmx_bp.route("", methods=["GET"])
@handle_exceptions()
def get_gmx_jobs(experiment_id: str) -> Response:
    """
    List all GROMACS jobs for an experiment.

    Returns:
        Response: JSON response with the list of GROMACS jobs.
    """
    schema = GromacsJobSchema(many=True)
    jobs: list[GromacsJob] = GromacsJob.query.filter_by(experiment_id=experiment_id).all()
    return jsonify(schema.dump(jobs))


@gmx_bp.route("/<path:tpr_name>", methods=["GET"])
@handle_exceptions()
def get_gmx_job(experiment_id: str, tpr_name: str) -> Response:
    """
    Get a specific GROMACS job by TPR name.

    Returns:
        Response: JSON response with the GROMACS job data.
    """
    schema = GromacsJobSchema()
    job: GromacsJob = GromacsJob.query.filter_by(experiment_id=experiment_id, tpr_name=tpr_name).first_or_404(
        description=f"GROMACS job for {tpr_name} in experiment {experiment_id} not found"
    )
    return jsonify(schema.dump(job))


@gmx_bp.route("/<path:tpr_name>", methods=["POST"])
@handle_exceptions(rollback=True)
def submit_gmx_job(experiment_id: str, tpr_name: str) -> Response:
    """
    Submit a new GROMACS simulation job.

    Returns:
        Response: JSON response with the created GROMACS job, or an error if the TPR file does not exist.
    """
    check_path(tpr_name, DATA_DIR / experiment_id)
    schema = GromacsJobSchema()
    experiment: Experiment = Experiment.query.get_or_404(
        experiment_id, description=f"Experiment {experiment_id} not found"
    )
    job: GromacsJob | None = GromacsJob.query.filter_by(experiment_id=experiment_id, tpr_name=tpr_name).first()
    tpr_path = DATA_DIR / experiment_id / tpr_name

    if not tpr_path.is_file():
        raise NotFound(f"TPR file {tpr_name} does not exist.")

    if not job:
        job = GromacsJob.start(
            experiment=experiment,
            tpr_path=tpr_path,
            pme=DeviceType.from_string(request.form["pme"]),
            nb=DeviceType.from_string(request.form["nb"]),
            np=int(request.form["np"]),
            ntomp=int(request.form["ntomp"]),
            extra_args=request.form.get("extra_args", ""),
        )

    return jsonify(schema.dump(job)), HTTPStatus.CREATED


@gmx_bp.route("/<path:tpr_name>", methods=["DELETE"])
@handle_exceptions(rollback=True)
def delete_gmx_job(experiment_id: str, tpr_name: str) -> Response:
    """
    Delete a GROMACS job and its associated Kubernetes resources.

    Returns:
        Response: Empty JSON response with 204 No Content on success.
    """
    job: GromacsJob = GromacsJob.query.filter_by(experiment_id=experiment_id, tpr_name=tpr_name).first_or_404(
        description=f"GROMACS job for {tpr_name} in experiment {experiment_id} not found"
    )
    job.delete()
    db.session.delete(job)
    db.session.commit()
    return "", HTTPStatus.NO_CONTENT


@gmx_bp.route("/<path:tpr_name>/log", methods=["GET"])
@handle_exceptions()
def get_gmx_job_log(experiment_id: str, tpr_name: str) -> Response:
    """
    Get log output for a GROMACS job.

    Returns:
        Response: JSON response with the requested log content.
    """
    job: GromacsJob = GromacsJob.query.filter_by(experiment_id=experiment_id, tpr_name=tpr_name).first_or_404(
        description=f"GROMACS job for {tpr_name} in experiment {experiment_id} not found"
    )

    log_type = request.args.get("type", "gmx").lower()
    tail_lines = request.args.get("tail", "10000")

    check_log_type(log_type)
    check_positive_int(tail_lines, "Tail lines", max_value=100000)

    log = job.get_log(log_type, int(tail_lines))
    return jsonify(log)