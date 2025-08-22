import logging
from http import HTTPStatus
from flask import Blueprint, request

from config import API_PREFIX
from api_response import ApiResponse
from models import MdrunJob
from schemas import JobCreateRequestSchema
from enums import DeviceType
from decorators import handle_exceptions
from extensions import db

logger = logging.getLogger(__name__)

mdrun_bp = Blueprint('mdrun', __name__, url_prefix=f'{API_PREFIX}/jobs')


@mdrun_bp.route('/<job_id>', methods=['GET'])
@handle_exceptions()
def get_job(job_id: str):
    job = MdrunJob.query.get_or_404(job_id, description=f'Job {job_id} not found')
    
    status_data = {
        'id': job.id,
        'status': job.status.value
    }
    
    return ApiResponse.success(status_data)


@mdrun_bp.route('', methods=['POST'])
@handle_exceptions(rollback=True)
def create_job():
    request_schema = JobCreateRequestSchema()
    data = request_schema.load(request.json)
    
    job = MdrunJob.create_and_start(
        experiment_id=data['experiment_id'],
        tpr_name=data['tpr_name'],
        pme=DeviceType.from_string(data['pme']),
        nb=DeviceType.from_string(data['nb']),
        np=data['np'],
        ntomp=data['ntomp'],
        extra_args=data.get('extra_args', '')
    )
    
    return ApiResponse.success({'id': job.id, 'status': job.status.value}, HTTPStatus.CREATED)


@mdrun_bp.route('/<job_id>', methods=['DELETE'])
@handle_exceptions(rollback=True)
def delete_job(job_id: str):
    job = MdrunJob.query.get_or_404(job_id, description=f'Job {job_id} not found')
    
    job.delete()
    db.session.delete(job)
    db.session.commit()
    
    return ApiResponse.success(f'Job {job_id} deleted successfully', HTTPStatus.NO_CONTENT)
