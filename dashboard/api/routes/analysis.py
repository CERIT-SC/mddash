import json
from http import HTTPStatus
from pathlib import Path

from clients import k8s
from config import API_PREFIX, DATA_DIR
from decorators import handle_exceptions
from enums import AnalysisType, PreprocessingMode
from extensions import db
from flask import Blueprint, Response, jsonify, request
from models import AnalysisJob, Experiment
from models.analysis_job import ANALYSIS_RESULT_PREFIX, ANALYSIS_RESULT_SUFFIX, find_result_file, list_result_files
from schemas import AnalysisJobSchema
from validators import check_path, validate_analysis_structure_path, validate_analysis_topology_path
from werkzeug.exceptions import BadRequest, NotFound, UnprocessableEntity

analysis_bp = Blueprint("analysis", __name__, url_prefix=f"{API_PREFIX}/experiments/<experiment_id>/analysis")


@analysis_bp.route("", methods=["GET"])
@handle_exceptions()
def get_analysis_jobs(experiment_id: str) -> Response:
    """
    List all analysis jobs for an experiment.

    Returns:
        JSON response with serialized list of analysis jobs.
    """
    schema = AnalysisJobSchema(many=True)
    jobs: list[AnalysisJob] = AnalysisJob.query.filter_by(experiment_id=experiment_id).all()
    return jsonify(schema.dump(jobs))


@analysis_bp.route("", methods=["POST"])
@handle_exceptions(rollback=True)
def submit_analysis_job(experiment_id: str) -> Response:
    """
    Submit a new analysis job. Rejects if a job is already running.

    Returns:
        JSON response with the created job on success, or an error response.
    """
    data = request.get_json()
    if not data:
        raise BadRequest("Request body is required.")

    analysis_name = data.get("analysis", "")
    structure_file = data.get("structure_file") or None
    trajectory_file = data.get("trajectory_file", "")
    if not analysis_name or not trajectory_file:
        raise BadRequest("analysis and trajectory_file are required.")

    try:
        analysis_type = AnalysisType(analysis_name)
    except ValueError:
        raise BadRequest(
            f"Unknown analysis '{analysis_name}'. Available: {', '.join(t.value for t in AnalysisType)}",
        )

    preprocessing_mode_name = data.get("preprocessing_mode", PreprocessingMode.AS_IS.value)
    try:
        preprocessing_mode = PreprocessingMode(preprocessing_mode_name)
    except ValueError:
        raise BadRequest(
            f"Unknown preprocessing_mode '{preprocessing_mode_name}'. Available: {', '.join(mode.value for mode in PreprocessingMode)}",
        )

    topology_file = data.get("topology_file") or None

    experiment_dir = DATA_DIR / experiment_id

    try:
        structure_path = validate_analysis_structure_path(
            structure_file=structure_file,
            topology_file=topology_file,
            experiment_dir=experiment_dir,
        )
    except BadRequest as error:
        raise error

    check_path(trajectory_file, experiment_dir)
    trajectory_path = Path(trajectory_file)
    if not (experiment_dir / trajectory_path).is_file():
        raise NotFound(f"Trajectory file {trajectory_path.as_posix()} does not exist.")

    try:
        topology_path = validate_analysis_topology_path(
            topology_file=topology_file,
            experiment_dir=experiment_dir,
            analysis_name=analysis_name,
            analysis_type=analysis_type,
            preprocessing_mode=preprocessing_mode,
        )
    except BadRequest as error:
        raise error

    job = AnalysisJob.start(
        experiment=Experiment.query.get_or_404(experiment_id, description=f"Experiment {experiment_id} not found"),
        analysis_name=analysis_type,
        structure_file=structure_path,
        trajectory_file=trajectory_path,
        topology_file=topology_path,
        preprocessing_mode=preprocessing_mode,
    )
    return jsonify(AnalysisJobSchema().dump(job)), HTTPStatus.CREATED


@analysis_bp.route("/<job_id>", methods=["GET"])
@handle_exceptions()
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
@handle_exceptions(rollback=True)
def delete_analysis_job(experiment_id: str, job_id: str) -> Response:
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
@handle_exceptions()
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


@analysis_bp.route("/results", methods=["GET"])
@handle_exceptions()
def list_analysis_results(experiment_id: str) -> Response:
    """
    List all available analysis result names for an experiment.

    Scans the mwf output directory directly so results remain visible even when no
    job records exist in the database (e.g., after deleting a failed job whose prior
    run had produced results).

    Returns:
        JSON response with a list of result name strings.
    """
    files = list_result_files(experiment_id)
    names = [f.name[len(ANALYSIS_RESULT_PREFIX) : -len(ANALYSIS_RESULT_SUFFIX)].replace("_", "-") for f in files]
    return jsonify(names)


@analysis_bp.route("/results/<name>/variants", methods=["GET"])
@handle_exceptions()
def get_analysis_variants(experiment_id: str, name: str) -> Response:
    """
    Return variant options for a multi-file analysis from its summary JSON.

    The summary file written by mwf for multi-file analyses is a list of
    {name, analysis} objects — one entry per interaction pair or run variant.

    Returns:
        JSON response with a list of variant objects, or an empty list if not found.
    """
    result_file = find_result_file(experiment_id, name)
    if not result_file:
        return jsonify([])

    try:
        data = json.loads(result_file.read_text())
    except (json.JSONDecodeError, UnicodeDecodeError):
        return jsonify([])

    # Summary format: [{ "name": "Overall", "analysis": "rmsd-pairwise-00" }, …]
    if isinstance(data, list) and all(
        isinstance(item, dict) and "analysis" in item and "name" in item for item in data
    ):
        return jsonify(data)

    return jsonify([])


@analysis_bp.route("/results/<name>", methods=["GET"])
@handle_exceptions()
def get_analysis_result(experiment_id: str, name: str) -> Response:
    """
    Get the JSON content of a specific analysis result.

    Returns:
        JSON response with the parsed analysis data, or an error response if not found.
    """
    result_file = find_result_file(experiment_id, name)
    if not result_file:
        raise NotFound(f"Analysis result '{name}' not found.")

    try:
        data = json.loads(result_file.read_text())
    except (json.JSONDecodeError, UnicodeDecodeError) as e:
        raise UnprocessableEntity(f"Failed to read analysis result: {e}")

    return jsonify(data)