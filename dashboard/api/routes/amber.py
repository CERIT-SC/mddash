from http import HTTPStatus

from config import API_PREFIX
from enums import AmberBinary, EwaldPreset
from extensions import db
from flask import Blueprint, Response, jsonify, request
from flask.typing import ResponseReturnValue
from models import AmberJob, Experiment
from schemas import AmberJobSchema
from validators import check_positive_int
from werkzeug.exceptions import BadRequest

amber_bp = Blueprint("amber", __name__, url_prefix=f"{API_PREFIX}/experiments/<experiment_id>/amber")


@amber_bp.route("", methods=["GET"])
def list_amber_jobs(experiment_id: str) -> Response:
    """
    List all AMBER jobs for an experiment.

    Returns:
        Response: JSON response with the list of AMBER jobs.
    """
    schema = AmberJobSchema(many=True)
    jobs: list[AmberJob] = AmberJob.query.filter_by(experiment_id=experiment_id).all()
    return jsonify(schema.dump(jobs))


@amber_bp.route("/<path:simulation_path>", methods=["GET"])
def get_amber_job(experiment_id: str, simulation_path: str) -> Response:
    """
    Get a specific AMBER job by simulation path.

    Returns:
        Response: JSON response with the AMBER job data.
    """
    schema = AmberJobSchema()
    job: AmberJob = AmberJob.query.filter_by(experiment_id=experiment_id, simulation_path=simulation_path).first_or_404(
        description=f"AMBER job for simulation {simulation_path} in experiment {experiment_id} not found"
    )
    return jsonify(schema.dump(job))


@amber_bp.route("/<path:simulation_path>", methods=["POST"])
def submit_amber_job(experiment_id: str, simulation_path: str) -> ResponseReturnValue:
    """
    Submit an AMBER simulation job from a simulation manifest.

    Body: ``{"binary": "pmemd.cuda", "ewald": "default", "np": 1, "ntomp": 8}``.

    Returns:
        Response: JSON response with the created AMBER job.

    Raises:
        BadRequest: If compute parameters are invalid.
    """
    schema = AmberJobSchema()
    experiment: Experiment = Experiment.query.get_or_404(
        experiment_id, description=f"Experiment {experiment_id} not found"
    )
    job: AmberJob | None = AmberJob.query.filter_by(
        experiment_id=experiment_id, simulation_path=simulation_path
    ).first()

    if not job:
        data = request.get_json(silent=True) or {}
        try:
            binary = AmberBinary.from_string(data.get("binary", request.form.get("binary", "")))
            ewald = EwaldPreset.from_string(data.get("ewald", request.form.get("ewald", "")))
            np = int(data.get("np", request.form.get("np", "")))
            ntomp = int(data.get("ntomp", request.form.get("ntomp", "")))
        except (ValueError, TypeError) as exc:
            raise BadRequest("Invalid compute parameters.") from exc

        job = AmberJob.start(
            experiment=experiment,
            simulation_path=simulation_path,
            binary=binary,
            ewald=ewald,
            np=np,
            ntomp=ntomp,
        )

    return jsonify(schema.dump(job)), HTTPStatus.CREATED


@amber_bp.route("/<path:simulation_path>", methods=["DELETE"])
def delete_amber_job(experiment_id: str, simulation_path: str) -> ResponseReturnValue:
    """
    Delete an AMBER job and its associated Kubernetes resources.

    Returns:
        Response: Empty JSON response with 204 No Content on success.
    """
    job: AmberJob = AmberJob.query.filter_by(experiment_id=experiment_id, simulation_path=simulation_path).first_or_404(
        description=f"AMBER job for simulation {simulation_path} in experiment {experiment_id} not found"
    )
    job.delete()
    db.session.delete(job)
    db.session.commit()
    return "", HTTPStatus.NO_CONTENT


@amber_bp.route("/<path:simulation_path>/log", methods=["GET"])
def get_amber_log(experiment_id: str, simulation_path: str) -> Response:
    """
    Get log output for an AMBER job.

    Returns:
        Response: JSON response with the requested log content.
    """
    job: AmberJob = AmberJob.query.filter_by(experiment_id=experiment_id, simulation_path=simulation_path).first_or_404(
        description=f"AMBER job for simulation {simulation_path} in experiment {experiment_id} not found"
    )

    log_type = request.args.get("type", "mdout").lower()
    tail_lines = request.args.get("tail", "10000")

    check_positive_int(tail_lines, "Tail lines", max_value=100000)

    log = job.get_log(log_type, int(tail_lines))
    return jsonify(log)
