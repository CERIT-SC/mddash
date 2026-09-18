from http import HTTPStatus

from config import API_PREFIX
from enums import DeviceType
from extensions import db
from flask import Blueprint, Response, jsonify, request
from flask.typing import ResponseReturnValue
from models import Experiment, GromacsJob
from models.simulation import SIMULATION_SUFFIX
from schemas import GromacsJobSchema
from validators import check_log_type, check_positive_int
from werkzeug.exceptions import BadRequest, NotFound

gmx_bp = Blueprint("gmx", __name__, url_prefix=f"{API_PREFIX}/experiments/<experiment_id>/gmx")


def _check_simulation_path(simulation_path: str) -> None:
    """
    Reject unknown verb suffixes swallowed by the greedy <path:> submit route.

    ``POST .../gmx/x.simulation.json/typo`` would otherwise validate the request
    body and 400 with "invalid compute parameters" instead of a clean 404.

    Raises:
        NotFound: If the path is not a simulation manifest path.
    """
    if not simulation_path.endswith(SIMULATION_SUFFIX):
        raise NotFound(f"Simulation {simulation_path} not found.")


def _latest_job_or_404(experiment_id: str, simulation_path: str) -> GromacsJob:
    """
    Latest (most recently created) segment of the simulation's run history.

    A simulation accumulates one job row per run/extension; every segment-scoped
    operation acts on the latest one.
    """
    return (
        GromacsJob.query
        .filter_by(experiment_id=experiment_id, simulation_path=simulation_path)
        .order_by(GromacsJob.created_at.desc())
        .first_or_404(
            description=f"GROMACS job for simulation {simulation_path} in experiment {experiment_id} not found"
        )
    )


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
    return jsonify(schema.dump(_latest_job_or_404(experiment_id, simulation_path)))


@gmx_bp.route("/<path:simulation_path>", methods=["POST"])
def submit_gmx_job(experiment_id: str, simulation_path: str) -> ResponseReturnValue:
    """
    Submit a GROMACS simulation job from a simulation manifest.

    Body: ``{"np": 4, "ntomp": 2, "pme": "cpu", "nb": "gpu"}``.

    Returns:
        Response: JSON response with the created GROMACS job.

    Raises:
        BadRequest: If compute parameters are invalid.
    """
    _check_simulation_path(simulation_path)

    schema = GromacsJobSchema()
    experiment: Experiment = Experiment.query.get_or_404(
        experiment_id, description=f"Experiment {experiment_id} not found"
    )
    job: GromacsJob | None = (
        GromacsJob.query
        .filter_by(experiment_id=experiment_id, simulation_path=simulation_path)
        .order_by(GromacsJob.created_at.desc())
        .first()
    )

    if not job:
        data = request.get_json(silent=True) or {}
        try:
            np = int(data.get("np", request.form.get("np", "")))
            ntomp = int(data.get("ntomp", request.form.get("ntomp", "")))
            pme = DeviceType.from_string(data.get("pme", request.form.get("pme", "")))
            nb = DeviceType.from_string(data.get("nb", request.form.get("nb", "")))
        except (ValueError, TypeError) as exc:
            raise BadRequest("Invalid compute parameters.") from exc

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
    Delete the whole run history: every segment's MDRun job, DB row, and result files.

    Returns:
        Response: Empty JSON response with 204 No Content on success.
    """
    jobs: list[GromacsJob] = GromacsJob.query.filter_by(
        experiment_id=experiment_id, simulation_path=simulation_path
    ).all()
    if not jobs:
        raise NotFound(f"GROMACS job for simulation {simulation_path} in experiment {experiment_id} not found")

    for job in jobs:
        job.delete()
        db.session.delete(job)
    db.session.commit()
    return "", HTTPStatus.NO_CONTENT


@gmx_bp.route("/<path:simulation_path>/stop", methods=["POST"])
def stop_gmx_job(experiment_id: str, simulation_path: str) -> ResponseReturnValue:
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


@gmx_bp.route("/<path:simulation_path>/extend", methods=["POST"])
def extend_gmx_job(experiment_id: str, simulation_path: str) -> ResponseReturnValue:
    """
    Extend a finished or stopped run by additional steps, resuming from its checkpoint.

    Body: ``{"nsteps": 100000}`` — steps to add on top of the current total.

    Returns:
        Response: JSON response with the created GROMACS job (the new segment), HTTP 201.

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
    Get log output for the latest segment of a GROMACS job.

    Returns:
        Response: JSON response with the requested log content.
    """
    job = _latest_job_or_404(experiment_id, simulation_path)

    log_type = request.args.get("type", "gmx").lower()
    tail_lines = request.args.get("tail", "10000")

    check_log_type(log_type)
    check_positive_int(tail_lines, "Tail lines", max_value=100000)

    log = job.get_log(log_type, int(tail_lines))
    return jsonify(log)
