from http import HTTPStatus
from flask import Blueprint, Response, request

from config import API_PREFIX, DATA_DIR
from api_response import ApiResponse
from models import Experiment, GromacsJob
from schemas import GromacsJobSchema
from extensions import db
from enums import DeviceType
from decorators import handle_exceptions
from utils import check_filename, check_log_type, check_positive_int


gmx_bp = Blueprint(
    'gmx',
    __name__,
    url_prefix=f'{API_PREFIX}/experiments/<experiment_id>/gmx'
)


@gmx_bp.route('', methods=['GET'])
@handle_exceptions()
def get_gmx_jobs(experiment_id: str) -> Response:
    schema = GromacsJobSchema(many=True)
    jobs: list[GromacsJob] = GromacsJob.query.filter_by(experiment_id=experiment_id).all()
    return ApiResponse.success(schema.dump(jobs))


@gmx_bp.route('/<tpr_name>', methods=['GET'])
@handle_exceptions()
def get_gmx_job(experiment_id: str, tpr_name: str) -> Response:
    schema = GromacsJobSchema()
    job: GromacsJob = GromacsJob.query.filter_by(experiment_id=experiment_id, tpr_name=tpr_name).first_or_404(description=f'GROMACS job for {tpr_name} in experiment {experiment_id} not found')
    return ApiResponse.success(schema.dump(job))


@gmx_bp.route('/<tpr_name>', methods=['POST'])
@handle_exceptions(rollback=True)
def submit_gmx_job(experiment_id: str, tpr_name: str) -> Response:
    check_filename(tpr_name, allowed_extensions=['tpr'])
    schema = GromacsJobSchema()
    experiment: Experiment = Experiment.query.get_or_404(experiment_id, description=f'Experiment {experiment_id} not found')
    job: GromacsJob = GromacsJob.query.filter_by(experiment_id=experiment_id, tpr_name=tpr_name).first()
    tpr_path = DATA_DIR / experiment_id / tpr_name

    if not tpr_path.exists():
        return ApiResponse.error(f'TPR file {tpr_name} does not exist.', HTTPStatus.NOT_FOUND)

    if not job:
        job = GromacsJob.start(
            experiment=experiment,
            tpr_path=tpr_path,
            pme=DeviceType.from_string(request.form['pme']),
            nb=DeviceType.from_string(request.form['nb']),
            np=int(request.form['np']),
            ntomp=int(request.form['ntomp']),
            extra_args=request.form.get('extra_args', ''),
        )

    return ApiResponse.success(schema.dump(job), HTTPStatus.CREATED)


@gmx_bp.route('/<tpr_name>', methods=['DELETE'])
@handle_exceptions(rollback=True)
def delete_gmx_job(experiment_id: str, tpr_name: str) -> Response:
    job: GromacsJob = GromacsJob.query.filter_by(experiment_id=experiment_id, tpr_name=tpr_name).first_or_404(description=f'GROMACS job for {tpr_name} in experiment {experiment_id} not found')
    job.delete()
    db.session.delete(job)
    db.session.commit()
    return ApiResponse.success(status=HTTPStatus.NO_CONTENT)


@gmx_bp.route('/<tpr_name>/log', methods=['GET'])
@handle_exceptions()
def get_gmx_job_log(experiment_id: str, tpr_name: str) -> Response:
    job: GromacsJob = GromacsJob.query.filter_by(experiment_id=experiment_id, tpr_name=tpr_name).first_or_404(description=f'GROMACS job for {tpr_name} in experiment {experiment_id} not found')
    
    log_type = request.args.get('type', 'gmx').lower()
    tail_lines = request.args.get('tail', '10000')

    check_log_type(log_type)
    check_positive_int(tail_lines, 'Tail lines', max_value=100000)

    log = job.get_log(log_type, int(tail_lines))
    return ApiResponse.success(log)
