from http import HTTPStatus

from config import API_PREFIX
from enums import DeviceType
from flask import Blueprint, Response, jsonify, request
from flask.typing import ResponseReturnValue
from models import Experiment, GromacsJob
from models.simulation import check_simulation_path
from schemas import GromacsJobSchema
from validators import check_log_type, check_positive_int
from werkzeug.exceptions import BadRequest, Conflict, NotFound

gmx_bp = Blueprint("gmx", __name__, url_prefix=f"{API_PREFIX}/experiments/<experiment_id>/gmx")


def _job_or_404(experiment_id: str, simulation_path: str) -> GromacsJob:
    """Return the simulation's single run row."""
    job = GromacsJob.current(experiment_id, simulation_path)
    if job is None:
        raise NotFound(f"GROMACS job for simulation {simulation_path} in experiment {experiment_id} not found")
    return job


@gmx_bp.route("", methods=["GET"])
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
def get_gmx_job(experiment_id: str, simulation_path: str) -> Response:
    """
    Get a specific GROMACS job by simulation path.

    Returns:
        Response: JSON response with the GROMACS job data.
    """
    schema = GromacsJobSchema()
    return jsonify(schema.dump(_job_or_404(experiment_id, simulation_path)))


@gmx_bp.route("/<path:simulation_path>", methods=["POST"])
def submit_gmx_job(experiment_id: str, simulation_path: str) -> ResponseReturnValue:
    """
    Submit a GROMACS simulation job from a simulation manifest.

    Body: ``{"np": 4, "ntomp": 2, "pme": "cpu", "nb": "gpu"}``.

    Returns:
        Response: JSON response with the created GROMACS job.

    Raises:
        BadRequest: If compute parameters are invalid.
        Conflict: If a live run already exists for this simulation.
    """
    check_simulation_path(simulation_path)

    schema = GromacsJobSchema()
    experiment: Experiment = Experiment.query.get_or_404(
        experiment_id, description=f"Experiment {experiment_id} not found"
    )

    prior = GromacsJob.current(experiment_id, simulation_path)
    if prior is not None and prior.is_live:
        raise Conflict("A run is already active for this simulation; stop it first to submit a new run.")

    data = request.get_json(silent=True) or {}
    try:
        np = int(data.get("np", request.form.get("np", "")))
        ntomp = int(data.get("ntomp", request.form.get("ntomp", "")))
        pme = DeviceType.from_string(data.get("pme", request.form.get("pme", "")))
        nb = DeviceType.from_string(data.get("nb", request.form.get("nb", "")))
    except (ValueError, TypeError) as exc:
        raise BadRequest("Invalid compute parameters.") from exc

    # A terminal run (finished, stopped, or failed) is replaced by the new one.
    GromacsJob.delete_current(experiment_id, simulation_path)

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
def delete_gmx_job(experiment_id: str, simulation_path: str) -> ResponseReturnValue:
    """
    Delete the simulation's run: its MDRun job, DB row, and result files.

    Returns:
        Response: Empty JSON response with 204 No Content on success.
    """
    if not GromacsJob.delete_current(experiment_id, simulation_path):
        raise NotFound(f"GROMACS job for simulation {simulation_path} in experiment {experiment_id} not found")

    return "", HTTPStatus.NO_CONTENT


@gmx_bp.route("/<path:simulation_path>/stop", methods=["POST"])
def stop_gmx_job(experiment_id: str, simulation_path: str) -> ResponseReturnValue:
    """
    Stop the run gracefully, keeping all data and the job row.

    Returns:
        Response: Empty JSON response with 204 No Content on success.

    Raises:
        BadRequest: If the run is not live.
    """
    job = _job_or_404(experiment_id, simulation_path)
    if not job.is_live:
        raise BadRequest("Only a live run can be stopped.")
    job.stop()
    return "", HTTPStatus.NO_CONTENT


@gmx_bp.route("/<path:simulation_path>/extend", methods=["POST"])
def extend_gmx_job(experiment_id: str, simulation_path: str) -> ResponseReturnValue:
    """
    Extend a finished or stopped run by additional steps, resuming from its checkpoint.

    Body: ``{"nsteps": 100000}`` — steps to add on top of the current total.

    Returns:
        Response: JSON response with the created GROMACS job (the extension), HTTP 201.

    Raises:
        BadRequest: If nsteps is invalid or the run cannot be extended.
    """
    schema = GromacsJobSchema()
    experiment: Experiment = Experiment.query.get_or_404(
        experiment_id, description=f"Experiment {experiment_id} not found"
    )

    data = request.get_json(silent=True) or {}
    try:
        nsteps = int(data.get("nsteps", request.form.get("nsteps", "")))
        if nsteps < 1:
            raise ValueError
    except (ValueError, TypeError) as exc:
        raise BadRequest("Invalid nsteps: must be a positive integer.") from exc

    job = GromacsJob.extend(experiment=experiment, simulation_path=simulation_path, nsteps=nsteps)
    return jsonify(schema.dump(job)), HTTPStatus.CREATED


@gmx_bp.route("/<path:simulation_path>/log", methods=["GET"])
def get_gmx_job_log(experiment_id: str, simulation_path: str) -> Response:
    """
    Get log output for a GROMACS job.

    Returns:
        Response: JSON response with the requested log content.
    """
    job = _job_or_404(experiment_id, simulation_path)

    log_type = request.args.get("type", "gmx").lower()
    tail_lines = request.args.get("tail", "10000")

    check_log_type(log_type)
    check_positive_int(tail_lines, "Tail lines", max_value=100000)

    log = job.get_log(log_type, int(tail_lines))
    return jsonify(log)
