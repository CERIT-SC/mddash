from http import HTTPStatus
from flask import Blueprint, Response

from config import API_PREFIX, DATA_DIR
from api_response import ApiResponse
from models import Experiment, TunerJob
from schemas import TunerJobSchema
from extensions import db


tuner_bp = Blueprint(
    'tuner',
    __name__,
    url_prefix=f'{API_PREFIX}/experiments/<experiment_id>/tuner'
)


@tuner_bp.route('', methods=['GET'])
def list_tuner_jobs(experiment_id: str) -> Response:
    schema = TunerJobSchema(many=True)

    try:
        tuner_jobs = TunerJob.query.filter_by(experiment_id=experiment_id).all()
        return ApiResponse.success(schema.dump(tuner_jobs))
    except Exception as e:
        return ApiResponse.error(e)


@tuner_bp.route('/<tpr_name>', methods=['GET'])
def get_tuner_job(experiment_id: str, tpr_name: str) -> Response:
    schema = TunerJobSchema()

    try:
        tuner_job: TunerJob = TunerJob.query.filter_by(experiment_id=experiment_id, tpr_name=tpr_name).first_or_404()
        return ApiResponse.success(schema.dump(tuner_job))
    except Exception as e:
        return ApiResponse.error(e)


@tuner_bp.route('/<tpr_name>', methods=['POST'])
def start_tuner_job(experiment_id: str, tpr_name: str) -> Response:
    schema = TunerJobSchema()

    try:
        experiment: Experiment = Experiment.query.get_or_404(experiment_id)
        tuner_job = TunerJob.query.filter_by(experiment_id=experiment_id, tpr_name=tpr_name).first()
        tpr_path = DATA_DIR / experiment_id / tpr_name

        if not tpr_path.exists():
            return ApiResponse.error(f'TPR file {tpr_name} does not exist.', HTTPStatus.NOT_FOUND)

        if not tuner_job:
            tuner_job = TunerJob.start(experiment, tpr_path)

        return ApiResponse.success(schema.dump(tuner_job), HTTPStatus.CREATED)
    
    except Exception as e:
        db.session.rollback()
        return ApiResponse.error(e)


@tuner_bp.route('/<tpr_name>', methods=['DELETE'])
def stop_tuner_job(experiment_id: str, tpr_name: str) -> Response:
    try:
        tuner_job: TunerJob = TunerJob.query.filter_by(experiment_id=experiment_id, tpr_name=tpr_name).first_or_404()
        tuner_job.delete()
        db.session.delete(tuner_job)
        db.session.commit()
        return ApiResponse.success(HTTPStatus.NO_CONTENT)
    except Exception as e:
        db.session.rollback()
        return ApiResponse.error(e)
