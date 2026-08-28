import json
from http import HTTPStatus
from typing import TYPE_CHECKING

from clients import k8s
from config import API_PREFIX
from enums import AnalysisType, Engine, PreprocessingMode
from extensions import db
from flask import Blueprint, Response, jsonify, request
from flask.typing import ResponseReturnValue
from models import AnalysisJob, Experiment
from models.analysis_job import ANALYSIS_RESULT_PREFIX, ANALYSIS_RESULT_SUFFIX, find_result_file, list_result_files
from models.simulation import Simulation
from schemas import AnalysisJobSchema, SubmitAnalysisSchema
from werkzeug.exceptions import BadRequest, NotFound, UnprocessableEntity

if TYPE_CHECKING:
    from pathlib import Path

analysis_bp = Blueprint("analysis", __name__, url_prefix=f"{API_PREFIX}/experiments/<experiment_id>/analysis")


@analysis_bp.route("", methods=["GET"])
def get_analysis_jobs(experiment_id: str) -> Response:
    """
    List analysis jobs for an experiment, optionally filtered by simulation.

    Query params:
        simulation_path: Filter jobs by simulation manifest path.

    Returns:
        JSON response with serialized list of analysis jobs.
    """
    query = AnalysisJob.query.filter_by(experiment_id=experiment_id)
    simulation_path = request.args.get("simulation_path")
    if simulation_path:
        query = query.filter_by(simulation_path=simulation_path)
    schema = AnalysisJobSchema(many=True)
    jobs: list[AnalysisJob] = query.all()
    return jsonify(schema.dump(jobs))


@analysis_bp.route("", methods=["POST"])
def submit_analysis_job(experiment_id: str) -> ResponseReturnValue:
    """
    Submit a new analysis job from a simulation manifest.

    Body: ``{"simulation_path": "...", "analysis": "...", "preprocessing_mode": "as-is"}``.

    Returns:
        JSON response with the created job on success, or an error response.

    Raises:
        BadRequest: If the request body is missing, invalid, or files are missing.
    """
    data = SubmitAnalysisSchema().load(request.get_json(silent=True) or {})

    simulation_path = data["simulation_path"]
    analysis_type: AnalysisType = data["analysis"]

    experiment = Experiment.query.get_or_404(experiment_id, description=f"Experiment {experiment_id} not found")
    simulation = Simulation.get(experiment_id, simulation_path)
    simulation.require_files(["trajectory"])

    trajectory_path = simulation.resolve_role("trajectory")

    preprocessing_mode: PreprocessingMode = data["preprocessing_mode"]

    if not trajectory_path.is_file():
        raise BadRequest(f"Trajectory file {trajectory_path} does not exist.")

    topology_path: Path | None = None
    if experiment.engine == Engine.GMX and "run_input" in simulation.files:
        topology_path = simulation.resolve_role("run_input")
    elif "topology" in simulation.files:
        topology_path = simulation.resolve_role("topology")

    structure_path: Path | None = None
    if "reference_structure" in simulation.files:
        structure_path = simulation.resolve_role("reference_structure")

    if preprocessing_mode in {PreprocessingMode.IMAGE, PreprocessingMode.IMAGE_FIT} and (
        not topology_path or topology_path.suffix.lower() != ".tpr"
    ):
        raise BadRequest("Trajectory preprocessing requires a simulation TPR file (.tpr).")

    analysis_topology_path = topology_path
    if experiment.engine == Engine.GMX and preprocessing_mode is PreprocessingMode.AS_IS and structure_path is not None:
        analysis_topology_path = None

    job = AnalysisJob.start(
        experiment=experiment,
        simulation_path=simulation_path,
        analysis_name=analysis_type,
        structure_file=structure_path,
        trajectory_file=trajectory_path,
        topology_file=analysis_topology_path,
        preprocessing_mode=preprocessing_mode,
    )
    return jsonify(AnalysisJobSchema().dump(job)), HTTPStatus.CREATED


@analysis_bp.route("/<job_id>", methods=["GET"])
def get_analysis_job(experiment_id: str, job_id: str) -> Response:
    """
    Get a specific analysis job by ID.

    Returns:
        JSON response with the serialized analysis job.
    """
    schema = AnalysisJobSchema()
    job: AnalysisJob = AnalysisJob.query.filter_by(experiment_id=experiment_id, id=job_id).first_or_404(
        description=f"Analysis job {job_id} in experiment {experiment_id} not found"
    )
    return jsonify(schema.dump(job))


@analysis_bp.route("/<job_id>", methods=["DELETE"])
def delete_analysis_job(experiment_id: str, job_id: str) -> ResponseReturnValue:
    """
    Delete an analysis job and its results.

    Returns:
        Empty 204 No Content response on success.
    """
    job: AnalysisJob = AnalysisJob.query.filter_by(experiment_id=experiment_id, id=job_id).first_or_404(
        description=f"Analysis job {job_id} in experiment {experiment_id} not found"
    )
    job.delete()
    db.session.delete(job)
    db.session.commit()
    return "", HTTPStatus.NO_CONTENT


@analysis_bp.route("/<job_id>/logs", methods=["GET"])
def get_analysis_job_logs(experiment_id: str, job_id: str) -> Response:
    """
    Get K8s pod logs for an analysis job.

    Returns:
        JSON response with log text, trimmed to content after the workflow start marker.
    """
    job: AnalysisJob = AnalysisJob.query.filter_by(experiment_id=experiment_id, id=job_id).first_or_404(
        description=f"Analysis job {job_id} in experiment {experiment_id} not found"
    )
    tail = request.args.get("tail", 200, type=int)
    tail = max(1, min(tail, 10_000))
    logs = k8s.get_job_logs(f"analysis-{job.id}", tail_lines=tail)
    # Strip initialization noise to avoid confusing users
    marker = "Running MDDB workflow"
    idx = logs.find(marker)
    return jsonify(logs[idx:] if idx != -1 else logs)


@analysis_bp.route("/types", methods=["GET"])
def list_analysis_types(experiment_id: str) -> Response:  # ruff: ignore[unused-function-argument]
    """
    List the mwf analysis task names the dashboard supports (the experiment-independent MDDB pool).

    Returns:
        Response: JSON array of analysis type ids.
    """
    return jsonify([analysis_type.value for analysis_type in AnalysisType])


@analysis_bp.route("/results", methods=["GET"])
def list_analysis_results(experiment_id: str) -> Response:
    """
    List available analysis result names for a simulation.

    Query params:
        simulation_path: Required — the simulation manifest path to scope results.

    Returns:
        JSON response with a list of result name strings.

    Raises:
        BadRequest: If simulation_path is missing.
    """
    simulation_path = request.args.get("simulation_path", "")
    if not simulation_path:
        raise BadRequest("simulation_path query parameter is required.")
    files = list_result_files(experiment_id, simulation_path)
    names = [f.name[len(ANALYSIS_RESULT_PREFIX) : -len(ANALYSIS_RESULT_SUFFIX)].replace("_", "-") for f in files]
    return jsonify(names)


@analysis_bp.route("/results/<name>/variants", methods=["GET"])
def get_analysis_variants(experiment_id: str, name: str) -> Response:
    """
    Return variant options for a multi-file analysis from its summary JSON.

    Query params:
        simulation_path: Required — the simulation manifest path to scope results.

    Returns:
        JSON response with a list of variant objects, or an empty list if not found.

    Raises:
        BadRequest: If simulation_path is missing.
    """
    simulation_path = request.args.get("simulation_path", "")
    if not simulation_path:
        raise BadRequest("simulation_path query parameter is required.")
    result_file = find_result_file(experiment_id, simulation_path, name)
    if not result_file:
        return jsonify([])

    try:
        data = json.loads(result_file.read_text())
    except (json.JSONDecodeError, UnicodeDecodeError):
        return jsonify([])

    if isinstance(data, list) and all(
        isinstance(item, dict) and "analysis" in item and "name" in item for item in data
    ):
        return jsonify(data)

    return jsonify([])


@analysis_bp.route("/results/<name>", methods=["GET"])
def get_analysis_result(experiment_id: str, name: str) -> Response:
    """
    Get the JSON content of a specific analysis result.

    Query params:
        simulation_path: Required — the simulation manifest path to scope results.

    Returns:
        JSON response with the parsed analysis data, or an error response if not found.

    Raises:
        BadRequest: If simulation_path is missing.
        NotFound: If the analysis result file does not exist.
        UnprocessableEntity: If the result file cannot be parsed as JSON.
    """
    simulation_path = request.args.get("simulation_path", "")
    if not simulation_path:
        raise BadRequest("simulation_path query parameter is required.")
    result_file = find_result_file(experiment_id, simulation_path, name)
    if not result_file:
        raise NotFound(f"Analysis result '{name}' not found.")

    try:
        data = json.loads(result_file.read_text())
    except (json.JSONDecodeError, UnicodeDecodeError) as e:
        raise UnprocessableEntity("Failed to read analysis result.") from e

    return jsonify(data)
