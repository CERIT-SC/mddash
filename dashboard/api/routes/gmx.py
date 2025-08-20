from http import HTTPStatus
from flask import Blueprint, Response, request

from config import API_PREFIX, DATA_DIR
from api_response import ApiResponse
from models import Experiment, GromacsJob
from schemas import GromacsJobSchema
from extensions import db
from enums import DeviceType


gmx_bp = Blueprint(
    'gmx',
    __name__,
    url_prefix=f'{API_PREFIX}/experiments/<experiment_id>/gmx'
)


@gmx_bp.route('', methods=['GET'])
def get_gmx_jobs(experiment_id: str) -> Response:
    schema = GromacsJobSchema(many=True)

    try:
        jobs: list[GromacsJob] = GromacsJob.query.filter_by(experiment_id=experiment_id).all()
        return ApiResponse.success(schema.dump(jobs))
    except Exception as e:
        return ApiResponse.error(e)


@gmx_bp.route('/<tpr_name>', methods=['GET'])
def get_gmx_job(experiment_id: str, tpr_name: str) -> Response:
    schema = GromacsJobSchema()

    try:
        job: GromacsJob = GromacsJob.query.filter_by(experiment_id=experiment_id, tpr_name=tpr_name).first_or_404()
        return ApiResponse.success(schema.dump(job))
    except Exception as e:
        return ApiResponse.error(e)


@gmx_bp.route('/<tpr_name>', methods=['POST'])
def submit_gmx_job(experiment_id: str, tpr_name: str) -> Response:
    schema = GromacsJobSchema()

    try:
        experiment = Experiment.query.filter_by(id=experiment_id).first_or_404()
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
    
    except Exception as e:
        db.session.rollback()
        return ApiResponse.error(e)


@gmx_bp.route('/<tpr_name>', methods=['DELETE'])
def delete_gmx_job(experiment_id: str, tpr_name: str) -> Response:
    try:
        job: GromacsJob = GromacsJob.query.filter_by(experiment_id=experiment_id, tpr_name=tpr_name).first_or_404()
        job.delete()
        db.session.delete(job)
        db.session.commit()
        return ApiResponse.success(f'Gromacs job {tpr_name} deleted successfully.', HTTPStatus.NO_CONTENT)
    except Exception as e:
        db.session.rollback()
        return ApiResponse.error(e)


@gmx_bp.route('/<tpr_name>/log', methods=['GET'])
def get_gmx_job_log(experiment_id: str, tpr_name: str) -> Response:
    try:
        job: GromacsJob = GromacsJob.query.filter_by(experiment_id=experiment_id, tpr_name=tpr_name).first_or_404()
        
        log_type = request.args.get('type', 'gmx').lower()
        tail_lines = request.args.get('tail', '10000')

        if log_type not in ['gmx', 'stdout', 'stderr']:
            return ApiResponse.error("Invalid log type. Use 'gmx', 'stdout', or 'stderr'.", HTTPStatus.BAD_REQUEST)

        if not tail_lines.isdigit():
            return ApiResponse.error("Tail lines must be a positive integer.", HTTPStatus.BAD_REQUEST)

        log = job.get_log(log_type, int(tail_lines))
        return ApiResponse.success(log)
    
    except Exception as e:
        return ApiResponse.error(e)
