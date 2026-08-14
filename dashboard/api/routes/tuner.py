from http import HTTPStatus

from clients import tuner
from config import API_PREFIX
from enums import Engine
from extensions import db
from flask import Blueprint, Response, jsonify, request
from flask.typing import ResponseReturnValue
from models import Experiment, TunerJob
from schemas import TunerJobSchema
from werkzeug.exceptions import BadRequest, InternalServerError, NotFound

tuner_bp = Blueprint("tuner", __name__, url_prefix=f"{API_PREFIX}/experiments/<experiment_id>/tuner")


@tuner_bp.route("", methods=["GET"])
def list_tuner_jobs(experiment_id: str) -> Response:
    """
    List all tuner jobs for an experiment.

    Returns:
        Response: JSON response with the list of tuner jobs.
    """
    schema = TunerJobSchema(many=True)
    tuner_jobs = TunerJob.query.filter_by(experiment_id=experiment_id).all()
    return jsonify(schema.dump(tuner_jobs))


@tuner_bp.route("", methods=["POST"])
def start_tuner_job(experiment_id: str) -> ResponseReturnValue:
    """
    Start a tuner job from a simulation manifest.

    Body: ``{"simulation_path": "...", "nsteps": 25000}``.

    Returns:
        Response: JSON response with the created or existing tuner job.

    Raises:
        NotFound: If the experiment or simulation_path is not found.
    """
    schema = TunerJobSchema()
    experiment: Experiment = Experiment.query.get_or_404(
        experiment_id, description=f"Experiment {experiment_id} not found"
    )

    data = request.get_json(silent=True) or {}
    simulation_path = data.get("simulation_path") or request.args.get("simulation_path")
    if not simulation_path:
        raise NotFound("simulation_path is required.")

    existing: TunerJob | None = TunerJob.query.filter_by(
        experiment_id=experiment_id, simulation_path=simulation_path
    ).first()

    if existing:
        if existing.error_message:
            existing.delete()
            db.session.delete(existing)
            db.session.commit()
        else:
            return jsonify(schema.dump(existing))

    # nsteps is always caller-supplied — reject the request instead of guessing a default.
    raw_nsteps = data.get("nsteps", request.args.get("nsteps"))
    if raw_nsteps is None:
        raise BadRequest("nsteps is required.")
    nsteps = int(raw_nsteps)

    tuner_job = TunerJob.start(experiment, simulation_path, nsteps=nsteps)
    return jsonify(schema.dump(tuner_job)), HTTPStatus.CREATED


@tuner_bp.route("/<path:simulation_path>", methods=["GET"])
def get_tuner_job(experiment_id: str, simulation_path: str) -> Response:
    """
    Get a specific tuner job by simulation path.

    Returns:
        Response: JSON response with the tuner job data.
    """
    schema = TunerJobSchema()
    tuner_job: TunerJob = TunerJob.query.filter_by(
        experiment_id=experiment_id, simulation_path=simulation_path
    ).first_or_404(description=f"Tuner job for {simulation_path} not found")
    return jsonify(schema.dump(tuner_job))


@tuner_bp.route("/<path:simulation_path>/stop", methods=["POST"])
def stop_tuner_job(experiment_id: str, simulation_path: str) -> ResponseReturnValue:
    """
    Stop a running tuner job.

    Returns:
        Response: Empty JSON response with 204 No Content on success.
    """
    tuner_job: TunerJob = TunerJob.query.filter_by(
        experiment_id=experiment_id, simulation_path=simulation_path
    ).first_or_404(description=f"Tuner job for {simulation_path} not found")
    tuner_job.stop()
    db.session.commit()
    return "", HTTPStatus.NO_CONTENT


@tuner_bp.route("/<path:simulation_path>/trials/<trial_id>/stdout", methods=["GET"])
def get_trial_stdout(experiment_id: str, simulation_path: str, trial_id: str) -> Response:
    """
    Get stdout log for a specific tuning trial.

    Returns:
        Response: JSON response with the stdout text.

    Raises:
        InternalServerError: If the engine is unknown.
    """
    tuner_job: TunerJob = TunerJob.query.filter_by(
        experiment_id=experiment_id, simulation_path=simulation_path
    ).first_or_404(description=f"Tuner job for {simulation_path} not found")
    match tuner_job.engine:
        case Engine.GMX:
            stdout = tuner.gmx_get_trial_stdout(tuner_job.id, trial_id)
        case Engine.AMBER:
            stdout = tuner.amber_get_trial_stdout(tuner_job.id, trial_id)
        case _:
            raise InternalServerError(f"Unknown engine: {tuner_job.engine}")
    return jsonify(stdout)


@tuner_bp.route("/<path:simulation_path>/trials/<trial_id>/stderr", methods=["GET"])
def get_trial_stderr(experiment_id: str, simulation_path: str, trial_id: str) -> Response:
    """
    Get stderr log for a specific tuning trial.

    Returns:
        Response: JSON response with the stderr text.

    Raises:
        InternalServerError: If the engine is unknown.
    """
    tuner_job: TunerJob = TunerJob.query.filter_by(
        experiment_id=experiment_id, simulation_path=simulation_path
    ).first_or_404(description=f"Tuner job for {simulation_path} not found")
    match tuner_job.engine:
        case Engine.GMX:
            stderr = tuner.gmx_get_trial_stderr(tuner_job.id, trial_id)
        case Engine.AMBER:
            stderr = tuner.amber_get_trial_stderr(tuner_job.id, trial_id)
        case _:
            raise InternalServerError(f"Unknown engine: {tuner_job.engine}")
    return jsonify(stderr)


@tuner_bp.route("/<path:simulation_path>", methods=["DELETE"])
def delete_tuner_job(experiment_id: str, simulation_path: str) -> ResponseReturnValue:
    """
    Delete a tuner job and its associated resources.

    Returns:
        Response: Empty JSON response with 204 No Content on success.
    """
    tuner_job: TunerJob = TunerJob.query.filter_by(
        experiment_id=experiment_id, simulation_path=simulation_path
    ).first_or_404(description=f"Tuner job for {simulation_path} not found")
    tuner_job.delete()
    db.session.delete(tuner_job)
    db.session.commit()
    return "", HTTPStatus.NO_CONTENT
