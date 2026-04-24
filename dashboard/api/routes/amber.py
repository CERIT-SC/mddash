from http import HTTPStatus

from api_response import ApiResponse
from config import API_PREFIX, DATA_DIR
from decorators import handle_exceptions
from enums import AmberBinary, EwaldPreset
from extensions import db
from flask import Blueprint, Response, request
from models import AmberJob, Experiment
from schemas import AmberJobSchema
from validators import check_path, check_positive_int

amber_bp = Blueprint("amber", __name__, url_prefix=f"{API_PREFIX}/experiments/<experiment_id>/amber")


@amber_bp.route("", methods=["GET"])
@handle_exceptions()
def list_amber_jobs(experiment_id: str) -> Response:
    """
    List all AMBER jobs for an experiment.

    Returns:
        Response: JSON response with the list of AMBER jobs.
    """
    schema = AmberJobSchema(many=True)
    jobs: list[AmberJob] = AmberJob.query.filter_by(experiment_id=experiment_id).all()
    return ApiResponse.success(schema.dump(jobs))


@amber_bp.route("/<path:prmtop_name>", methods=["GET"])
@handle_exceptions()
def get_amber_job(experiment_id: str, prmtop_name: str) -> Response:
    """
    Get a specific AMBER job by PRMTOP name.

    Returns:
        Response: JSON response with the AMBER job data.
    """
    schema = AmberJobSchema()
    job: AmberJob = AmberJob.query.filter_by(experiment_id=experiment_id, prmtop_name=prmtop_name).first_or_404(
        description=f"AMBER job for {prmtop_name} in experiment {experiment_id} not found"
    )
    return ApiResponse.success(schema.dump(job))


@amber_bp.route("/<path:prmtop_name>", methods=["POST"])
@handle_exceptions(rollback=True)
def submit_amber_job(experiment_id: str, prmtop_name: str) -> Response:
    """
    Submit a new AMBER simulation job.

    Returns:
        Response: JSON response with the created AMBER job, or an error if files do not exist.
    """
    check_path(prmtop_name, DATA_DIR / experiment_id)
    schema = AmberJobSchema()
    experiment: Experiment = Experiment.query.get_or_404(
        experiment_id, description=f"Experiment {experiment_id} not found"
    )
    job: AmberJob | None = AmberJob.query.filter_by(experiment_id=experiment_id, prmtop_name=prmtop_name).first()
    prmtop_path = DATA_DIR / experiment_id / prmtop_name

    if not prmtop_path.is_file():
        return ApiResponse.error(f"PRMTOP file {prmtop_name} does not exist.", HTTPStatus.NOT_FOUND)

    if not job:
        inpcrd_name = request.form["inpcrd_name"]
        mdin_name = request.form["mdin_name"]

        check_path(inpcrd_name, DATA_DIR / experiment_id)
        check_path(mdin_name, DATA_DIR / experiment_id)

        inpcrd_path = DATA_DIR / experiment_id / inpcrd_name
        mdin_path = DATA_DIR / experiment_id / mdin_name

        if not inpcrd_path.is_file():
            return ApiResponse.error(f"INPCRD file {inpcrd_name} does not exist.", HTTPStatus.NOT_FOUND)
        if not mdin_path.is_file():
            return ApiResponse.error(f"MDIN file {mdin_name} does not exist.", HTTPStatus.NOT_FOUND)

        binary = AmberBinary.from_string(request.form["binary"])
        ewald = EwaldPreset.from_string(request.form["ewald"])
        np = int(request.form["np"])
        ntomp = int(request.form["ntomp"])
        extra_args = request.form.get("extra_args", "")

        job = AmberJob.start(
            experiment=experiment,
            prmtop_path=prmtop_path,
            inpcrd_path=inpcrd_path,
            mdin_path=mdin_path,
            binary=binary,
            ewald=ewald,
            np=np,
            ntomp=ntomp,
            extra_args=extra_args,
        )

    return ApiResponse.success(schema.dump(job), HTTPStatus.CREATED)


@amber_bp.route("/<path:prmtop_name>", methods=["DELETE"])
@handle_exceptions(rollback=True)
def delete_amber_job(experiment_id: str, prmtop_name: str) -> Response:
    """
    Delete an AMBER job and its associated Kubernetes resources.

    Returns:
        Response: Empty JSON response with 204 No Content on success.
    """
    job: AmberJob = AmberJob.query.filter_by(experiment_id=experiment_id, prmtop_name=prmtop_name).first_or_404(
        description=f"AMBER job for {prmtop_name} in experiment {experiment_id} not found"
    )
    job.delete()
    db.session.delete(job)
    db.session.commit()
    return ApiResponse.success(status=HTTPStatus.NO_CONTENT)


@amber_bp.route("/<path:prmtop_name>/log", methods=["GET"])
@handle_exceptions()
def get_amber_log(experiment_id: str, prmtop_name: str) -> Response:
    """
    Get log output for an AMBER job.

    Returns:
        Response: JSON response with the requested log content.
    """
    job: AmberJob = AmberJob.query.filter_by(experiment_id=experiment_id, prmtop_name=prmtop_name).first_or_404(
        description=f"AMBER job for {prmtop_name} in experiment {experiment_id} not found"
    )

    log_type = request.args.get("type", "amber").lower()
    tail_lines = request.args.get("tail", "10000")

    check_positive_int(tail_lines, "Tail lines", max_value=100000)

    log = job.get_log(log_type, int(tail_lines))
    return ApiResponse.success(log)
