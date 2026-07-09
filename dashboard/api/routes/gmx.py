from http import HTTPStatus

from config import API_PREFIX
from decorators import handle_exceptions
from enums import DeviceType
from extensions import db
from flask import Blueprint, Response, jsonify, request
from flask.typing import ResponseReturnValue
from models import Experiment, GromacsJob
from schemas import GromacsJobSchema
from validators import check_log_type, check_positive_int
from werkzeug.exceptions import BadRequest

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


@gmx_bp.route("/<path:simulation_path>", methods=["GET"])
@handle_exceptions()
def get_gmx_job(experiment_id: str, simulation_path: str) -> Response:
    """
    Get a specific GROMACS job by simulation path.

    Returns:
        Response: JSON response with the GROMACS job data.
    """
    schema = GromacsJobSchema()
    job: GromacsJob = GromacsJob.query.filter_by(
        experiment_id=experiment_id, simulation_path=simulation_path
    ).first_or_404(description=f"GROMACS job for simulation {simulation_path} in experiment {experiment_id} not found")
    return jsonify(schema.dump(job))


@gmx_bp.route("/<path:simulation_path>", methods=["POST"])
@handle_exceptions(rollback=True)
def submit_gmx_job(experiment_id: str, simulation_path: str) -> ResponseReturnValue:
    """
    Submit a GROMACS simulation job from a simulation manifest.

    Body: ``{"np": 4, "ntomp": 2, "pme": "cpu", "nb": "gpu"}``.

    Returns:
        Response: JSON response with the created GROMACS job.

    Raises:
        BadRequest: If compute parameters are invalid.
    """
    schema = GromacsJobSchema()
    experiment: Experiment = Experiment.query.get_or_404(
        experiment_id, description=f"Experiment {experiment_id} not found"
    )
    job: GromacsJob | None = GromacsJob.query.filter_by(
        experiment_id=experiment_id, simulation_path=simulation_path
    ).first()

    if not job:
        data = request.get_json(silent=True) or {}
        try:
            np = int(data.get("np", request.form.get("np", "")))
            ntomp = int(data.get("ntomp", request.form.get("ntomp", "")))
            pme = DeviceType.from_string(data.get("pme", request.form.get("pme", "")))
            nb = DeviceType.from_string(data.get("nb", request.form.get("nb", "")))
        except (ValueError, TypeError) as exc:
            raise BadRequest(f"Invalid compute parameters: {exc}") from exc

        job = GromacsJob.start(
            experiment=experiment,
            simulation_path=simulation_path,
            pme=pme,
            nb=nb,
            np=np,
            ntomp=ntomp,
        )

    return jsonify(schema.dump(job)), HTTPStatus.CREATED


@gmx_bp.route("/<path:simulation_path>", methods=["DELETE"])
@handle_exceptions(rollback=True)
def delete_gmx_job(experiment_id: str, simulation_path: str) -> ResponseReturnValue:
    """
    Delete a GROMACS job and its associated Kubernetes resources.

    Returns:
        Response: Empty JSON response with 204 No Content on success.
    """
    job: GromacsJob = GromacsJob.query.filter_by(
        experiment_id=experiment_id, simulation_path=simulation_path
    ).first_or_404(description=f"GROMACS job for simulation {simulation_path} in experiment {experiment_id} not found")
    job.delete()
    db.session.delete(job)
    db.session.commit()
    return "", HTTPStatus.NO_CONTENT


@gmx_bp.route("/<path:simulation_path>/log", methods=["GET"])
@handle_exceptions()
def get_gmx_job_log(experiment_id: str, simulation_path: str) -> Response:
    """
    Get log output for a GROMACS job.

    Returns:
        Response: JSON response with the requested log content.
    """
    job: GromacsJob = GromacsJob.query.filter_by(
        experiment_id=experiment_id, simulation_path=simulation_path
    ).first_or_404(description=f"GROMACS job for simulation {simulation_path} in experiment {experiment_id} not found")

    log_type = request.args.get("type", "gmx").lower()
    tail_lines = request.args.get("tail", "10000")

    check_log_type(log_type)
    check_positive_int(tail_lines, "Tail lines", max_value=100000)

    log = job.get_log(log_type, int(tail_lines))
    return jsonify(log)
