from http import HTTPStatus
from flask import Blueprint, Response

from config import API_PREFIX, DATA_DIR
from api_response import ApiResponse
from models import Experiment, TunerJob
from schemas import TunerJobSchema
from extensions import db
from decorators import handle_exceptions


tuner_bp = Blueprint(
    'tuner',
    __name__,
    url_prefix=f'{API_PREFIX}/experiments/<experiment_id>/tuner'
)


@tuner_bp.route('', methods=['GET'])
@handle_exceptions()
def list_tuner_jobs(experiment_id: str) -> Response:
    schema = TunerJobSchema(many=True)
    tuner_jobs = TunerJob.query.filter_by(experiment_id=experiment_id).all()
    return ApiResponse.success(schema.dump(tuner_jobs))


@tuner_bp.route('/<tpr_name>', methods=['GET'])
@handle_exceptions()
def get_tuner_job(experiment_id: str, tpr_name: str) -> Response:
    schema = TunerJobSchema()
    tuner_job: TunerJob = TunerJob.query.filter_by(experiment_id=experiment_id, tpr_name=tpr_name).first_or_404(description=f'Tuner job for {tpr_name} not found')
    return ApiResponse.success(schema.dump(tuner_job))


@tuner_bp.route('/<tpr_name>', methods=['POST'])
@handle_exceptions(rollback=True)
def start_tuner_job(experiment_id: str, tpr_name: str) -> Response:
    schema = TunerJobSchema()
    experiment: Experiment = Experiment.query.get_or_404(experiment_id, description=f'Experiment {experiment_id} not found')
    tuner_job = TunerJob.query.filter_by(experiment_id=experiment_id, tpr_name=tpr_name).first()
    tpr_path = DATA_DIR / experiment_id / tpr_name

    if not tpr_path.exists():
        return ApiResponse.error(f'TPR file {tpr_name} does not exist.', HTTPStatus.NOT_FOUND)

    if not tuner_job:
        tuner_job = TunerJob.start(experiment, tpr_path)

    return ApiResponse.success(schema.dump(tuner_job), HTTPStatus.CREATED)


@tuner_bp.route('/<tpr_name>/stop', methods=['POST'])
@handle_exceptions(rollback=True)
def stop_tuner_job(experiment_id: str, tpr_name: str) -> Response:
    tuner_job: TunerJob = TunerJob.query.filter_by(experiment_id=experiment_id, tpr_name=tpr_name).first_or_404(description=f'Tuner job for {tpr_name} not found')
    tuner_job.stop()
    db.session.commit()
    return ApiResponse.success(status=HTTPStatus.NO_CONTENT)


@tuner_bp.route('/<tpr_name>', methods=['DELETE'])
@handle_exceptions(rollback=True)
def delete_tuner_job(experiment_id: str, tpr_name: str) -> Response:
    tuner_job: TunerJob = TunerJob.query.filter_by(experiment_id=experiment_id, tpr_name=tpr_name).first_or_404(description=f'Tuner job for {tpr_name} not found')
    tuner_job.delete()
    db.session.delete(tuner_job)
    db.session.commit()
    return ApiResponse.success(status=HTTPStatus.NO_CONTENT)
