from http import HTTPStatus
from flask import Blueprint, Response

from config import API_PREFIX
from api_response import ApiResponse
from models import Experiment, Notebook
from schemas import NotebookSchema
from extensions import db


notebook_bp = Blueprint(
    'notebook',
    __name__,
    url_prefix=f'{API_PREFIX}/experiments/<experiment_id>/notebook'
)


@notebook_bp.route('', methods=['GET'])
def get_notebook(experiment_id: str) -> Response:
    schema = NotebookSchema()

    try:
        experiment: Experiment = Experiment.query.get_or_404(experiment_id, description=f'Experiment {experiment_id} not found')
        
        return ApiResponse.success(schema.dump(experiment.notebook))
    except Exception as e:
        return ApiResponse.error(e)


@notebook_bp.route('', methods=['POST'])
def start_notebook(experiment_id: str) -> Response:
    schema = NotebookSchema()

    try:
        experiment: Experiment = Experiment.query.get_or_404(experiment_id, description=f'Experiment {experiment_id} not found')
        
        notebook = experiment.notebook
        notebook.start()
        db.session.commit()

        return ApiResponse.success(schema.dump(notebook), HTTPStatus.CREATED)

    except Exception as e:
        db.session.rollback()
        return ApiResponse.error(e)


@notebook_bp.route('', methods=['DELETE'])
def stop_notebook(experiment_id: str) -> Response:
    try:
        experiment: Experiment = Experiment.query.get_or_404(experiment_id, description=f'Experiment {experiment_id} not found')
        
        notebook = experiment.notebook
        notebook.stop()
        return ApiResponse.success(HTTPStatus.NO_CONTENT)
    except Exception as e:
        return ApiResponse.error(e)
