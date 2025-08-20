from http import HTTPStatus
from flask import Blueprint
from werkzeug.exceptions import HTTPException

from config import API_PREFIX
from api_response import ApiResponse, Response
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
        notebook: Notebook = Notebook.query.filter_by(experiment_id=experiment_id).first_or_404()
        return ApiResponse.success(schema.dump(notebook))
    except Exception as e:
        return ApiResponse.error(e)


@notebook_bp.route('', methods=['POST'])
def start_notebook(experiment_id: str) -> Response:
    schema = NotebookSchema()
    
    try:
        experiment: Experiment = Experiment.query.get_or_404(experiment_id)
        notebook = experiment.notebook or Notebook(experiment=experiment)

        if not experiment.notebook:
            db.session.add(notebook)
            db.session.commit()

        notebook.start()
        return ApiResponse.success(schema.dump(notebook), status=HTTPStatus.CREATED)

    except Exception as e:
        db.session.rollback()
        return ApiResponse.error(e)


@notebook_bp.route('', methods=['DELETE'])
def stop_notebook(experiment_id: str) -> Response:
    try:
        notebook: Notebook = Notebook.query.filter_by(experiment_id=experiment_id).first_or_404()
        notebook.stop()
        return ApiResponse.success(status=HTTPStatus.NO_CONTENT)
    except Exception as e:
        return ApiResponse.error(e)
