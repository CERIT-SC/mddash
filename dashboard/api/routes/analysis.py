import json
from http import HTTPStatus

from api_response import ApiResponse
from config import API_PREFIX, DATA_DIR
from decorators import handle_exceptions
from enums import AnalysisType, JobStatus
from extensions import db
from flask import Blueprint, Response, request
from models import AnalysisJob, Experiment
from models.analysis_job import ANALYSIS_RESULT_PREFIX, ANALYSIS_RESULT_SUFFIX
from schemas import AnalysisJobSchema
from validators import check_path

analysis_bp = Blueprint("analysis", __name__, url_prefix=f"{API_PREFIX}/experiments/<experiment_id>/analysis")


@analysis_bp.route("", methods=["GET"])
@handle_exceptions()
def get_analysis_jobs(experiment_id: str) -> Response:
    """List all analysis jobs for an experiment."""
    schema = AnalysisJobSchema(many=True)
    jobs: list[AnalysisJob] = AnalysisJob.query.filter_by(experiment_id=experiment_id).all()
    return ApiResponse.success(schema.dump(jobs))


@analysis_bp.route("", methods=["POST"])
@handle_exceptions(rollback=True)
def submit_analysis_job(experiment_id: str) -> Response:
    """Submit a new analysis job. Rejects if a job is already running."""
    data = request.get_json()
    if not data:
        return ApiResponse.error("Request body is required.", HTTPStatus.BAD_REQUEST)

    analysis_name = data.get("analysis", "")
    structure_file = data.get("structure_file", "")
    trajectory_file = data.get("trajectory_file", "")

    if not analysis_name or not structure_file or not trajectory_file:
        return ApiResponse.error("analysis, structure_file, and trajectory_file are required.", HTTPStatus.BAD_REQUEST)

    try:
        analysis_type = AnalysisType(analysis_name)
    except ValueError:
        available = ", ".join(t.value for t in AnalysisType)
        return ApiResponse.error(
            f"Unknown analysis '{analysis_name}'. Available: {available}",
            HTTPStatus.BAD_REQUEST,
        )

    experiment_dir = DATA_DIR / experiment_id
    check_path(structure_file, experiment_dir)
    check_path(trajectory_file, experiment_dir)

    if not (experiment_dir / structure_file).is_file():
        return ApiResponse.error(f"Structure file {structure_file} does not exist.", HTTPStatus.NOT_FOUND)
    if not (experiment_dir / trajectory_file).is_file():
        return ApiResponse.error(f"Trajectory file {trajectory_file} does not exist.", HTTPStatus.NOT_FOUND)

    experiment: Experiment = Experiment.query.get_or_404(
        experiment_id, description=f"Experiment {experiment_id} not found"
    )

    # Reject if any analysis job is already active
    active_jobs = AnalysisJob.query.filter_by(experiment_id=experiment_id).all()
    for job in active_jobs:
        if job.status in {JobStatus.RUNNING, JobStatus.PENDING}:
            return ApiResponse.error("An analysis job is already running.", HTTPStatus.CONFLICT)

    schema = AnalysisJobSchema()
    job = AnalysisJob.start(
        experiment=experiment,
        analysis_name=analysis_type,
        structure_file=structure_file,
        trajectory_file=trajectory_file,
    )
    return ApiResponse.success(schema.dump(job), HTTPStatus.CREATED)


@analysis_bp.route("/<job_id>", methods=["GET"])
@handle_exceptions()
def get_analysis_job(experiment_id: str, job_id: str) -> Response:
    """Get a specific analysis job by ID."""
    schema = AnalysisJobSchema()
    job: AnalysisJob = AnalysisJob.query.filter_by(experiment_id=experiment_id, id=job_id).first_or_404(
        description=f"Analysis job {job_id} in experiment {experiment_id} not found"
    )
    return ApiResponse.success(schema.dump(job))


@analysis_bp.route("/<job_id>", methods=["DELETE"])
@handle_exceptions(rollback=True)
def delete_analysis_job(experiment_id: str, job_id: str) -> Response:
    """Delete an analysis job and its results."""
    job: AnalysisJob = AnalysisJob.query.filter_by(experiment_id=experiment_id, id=job_id).first_or_404(
        description=f"Analysis job {job_id} in experiment {experiment_id} not found"
    )
    job.delete()
    db.session.delete(job)
    db.session.commit()
    return ApiResponse.success(status=HTTPStatus.NO_CONTENT)


@analysis_bp.route("/results", methods=["GET"])
@handle_exceptions()
def list_analysis_results(experiment_id: str) -> Response:
    """List available analysis result files."""
    experiment_dir = DATA_DIR / experiment_id
    if not experiment_dir.is_dir():
        return ApiResponse.success([])

    results = []
    for f in sorted(experiment_dir.iterdir()):
        if f.is_file() and f.name.startswith(ANALYSIS_RESULT_PREFIX) and f.name.endswith(ANALYSIS_RESULT_SUFFIX):
            name = f.name[len(ANALYSIS_RESULT_PREFIX) : -len(ANALYSIS_RESULT_SUFFIX)]
            results.append({"name": name, "file": f.name})

    return ApiResponse.success(results)


@analysis_bp.route("/results/<name>", methods=["GET"])
@handle_exceptions()
def get_analysis_result(experiment_id: str, name: str) -> Response:
    """Get the JSON content of a specific analysis result."""
    result_file = DATA_DIR / experiment_id / f"{ANALYSIS_RESULT_PREFIX}{name}{ANALYSIS_RESULT_SUFFIX}"

    if not result_file.is_file():
        return ApiResponse.error(f"Analysis result '{name}' not found.", HTTPStatus.NOT_FOUND)

    # Validate the path stays within the experiment directory
    check_path(result_file.name, DATA_DIR / experiment_id)

    try:
        data = json.loads(result_file.read_text())
    except (json.JSONDecodeError, UnicodeDecodeError) as e:
        return ApiResponse.error(f"Failed to read analysis result: {e}", HTTPStatus.UNPROCESSABLE_ENTITY)

    return ApiResponse.success(data)
