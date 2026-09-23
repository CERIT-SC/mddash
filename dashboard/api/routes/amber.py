from http import HTTPStatus

from config import API_PREFIX
from enums import AmberBinary, EwaldPreset
from extensions import db
from flask import Blueprint, Response, jsonify, request
from flask.typing import ResponseReturnValue
from models import AmberJob, Experiment
from models.simulation import check_simulation_path
from schemas import AmberJobSchema
from validators import check_positive_int
from werkzeug.exceptions import BadRequest, Conflict, NotFound

amber_bp = Blueprint("amber", __name__, url_prefix=f"{API_PREFIX}/experiments/<experiment_id>/amber")


def _latest_job_or_404(experiment_id: str, simulation_path: str) -> AmberJob:
    """Latest (most recently created) segment of the simulation's run history."""
    job = AmberJob.latest_for(experiment_id, simulation_path)
    if job is None:
        raise NotFound(f"AMBER job for simulation {simulation_path} in experiment {experiment_id} not found")
    return job


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
    return jsonify(schema.dump(_latest_job_or_404(experiment_id, simulation_path)))


@amber_bp.route("/<path:simulation_path>", methods=["POST"])
def submit_amber_job(experiment_id: str, simulation_path: str) -> ResponseReturnValue:
    """
    Submit an AMBER simulation job from a simulation manifest.

    Body: ``{"binary": "pmemd.cuda", "ewald": "default", "np": 1, "ntomp": 8}``.

    Returns:
        Response: JSON response with the created AMBER job.

    Raises:
        BadRequest: If compute parameters are invalid.
        Conflict: If a run already exists for this simulation.
    """
    check_simulation_path(simulation_path)

    schema = AmberJobSchema()
    experiment: Experiment = Experiment.query.get_or_404(
        experiment_id, description=f"Experiment {experiment_id} not found"
    )

    if AmberJob.latest_for(experiment_id, simulation_path) is not None:
        raise Conflict("A run already exists for this simulation; delete it first to submit a new run.")

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
    Delete the whole run history: every segment's MDRun job, DB row, and result files.

    Returns:
        Response: Empty JSON response with 204 No Content on success.
    """
    jobs: list[AmberJob] = AmberJob.query.filter_by(experiment_id=experiment_id, simulation_path=simulation_path).all()
    if not jobs:
        raise NotFound(f"AMBER job for simulation {simulation_path} in experiment {experiment_id} not found")

    for job in jobs:
        job.delete()
        db.session.delete(job)
    db.session.commit()
    return "", HTTPStatus.NO_CONTENT


@amber_bp.route("/<path:simulation_path>/stop", methods=["POST"])
def stop_amber_job(experiment_id: str, simulation_path: str) -> ResponseReturnValue:
    """
    Stop the latest run segment gracefully, keeping all data and job history.

    Returns:
        Response: Empty JSON response with 204 No Content on success.

    Raises:
        BadRequest: If the latest segment is not live.
    """
    job = _latest_job_or_404(experiment_id, simulation_path)
    if not job.is_live:
        raise BadRequest("Only a live run can be stopped.")
    job.stop()
    return "", HTTPStatus.NO_CONTENT


@amber_bp.route("/<path:simulation_path>/extend", methods=["POST"])
def extend_amber_job(experiment_id: str, simulation_path: str) -> ResponseReturnValue:
    """
    Reject AMBER extension requests; extension is only available for GROMACS.

    Exists so that ``POST .../extend`` is a clear 400 instead of falling into the
    greedy submit route with confusing parameter errors.
    """
    check_simulation_path(simulation_path)
    _ = experiment_id
    raise BadRequest("Simulation extension is only available for GROMACS.")


@amber_bp.route("/<path:simulation_path>/log", methods=["GET"])
def get_amber_log(experiment_id: str, simulation_path: str) -> Response:
    """
    Get log output for the latest segment of an AMBER job.

    Returns:
        Response: JSON response with the requested log content.
    """
    job = _latest_job_or_404(experiment_id, simulation_path)

    log_type = request.args.get("type", "mdout").lower()
    tail_lines = request.args.get("tail", "10000")

    check_positive_int(tail_lines, "Tail lines", max_value=100000)

    log = job.get_log(log_type, int(tail_lines))
    return jsonify(log)
