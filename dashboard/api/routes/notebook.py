from http import HTTPStatus
from flask import Blueprint, Response

from config import API_PREFIX
from api_response import ApiResponse
from models import Experiment
from schemas import NotebookSchema
from extensions import db
from decorators import handle_exceptions


notebook_bp = Blueprint(
    'notebook',
    __name__,
    url_prefix=f'{API_PREFIX}/experiments/<experiment_id>/notebook'
)


@notebook_bp.route('', methods=['GET'])
@handle_exceptions()
def get_notebook(experiment_id: str) -> Response:
    schema = NotebookSchema()
    experiment: Experiment = Experiment.query.get_or_404(experiment_id, description=f'Experiment {experiment_id} not found')
    return ApiResponse.success(schema.dump(experiment.notebook))


@notebook_bp.route('', methods=['POST'])
@handle_exceptions(rollback=True)
def start_notebook(experiment_id: str) -> Response:
    schema = NotebookSchema()
    experiment: Experiment = Experiment.query.get_or_404(experiment_id, description=f'Experiment {experiment_id} not found')
    notebook = experiment.notebook
    notebook.start()
    db.session.commit()
    return ApiResponse.success(schema.dump(notebook), HTTPStatus.CREATED)


@notebook_bp.route('', methods=['DELETE'])
@handle_exceptions()
def stop_notebook(experiment_id: str) -> Response:
    experiment: Experiment = Experiment.query.get_or_404(experiment_id, description=f'Experiment {experiment_id} not found')
    notebook = experiment.notebook
    notebook.stop()
    return ApiResponse.success(HTTPStatus.NO_CONTENT)
