from http import HTTPStatus

from api_response import ApiResponse
from config import API_PREFIX
from decorators import handle_exceptions
from extensions import db
from flask import Blueprint, Response
from models import Experiment
from schemas import NotebookSchema

notebook_bp = Blueprint("notebook", __name__, url_prefix=f"{API_PREFIX}/experiments/<experiment_id>/notebook")


@notebook_bp.route("", methods=["GET"])
@handle_exceptions()
def get_notebook(experiment_id: str) -> Response:
    """Get the notebook instance for an experiment."""
    schema = NotebookSchema()
    experiment: Experiment = Experiment.query.get_or_404(
        experiment_id, description=f"Experiment {experiment_id} not found"
    )
    return ApiResponse.success(schema.dump(experiment.notebook))


@notebook_bp.route("", methods=["POST"])
@handle_exceptions(rollback=True)
def start_notebook(experiment_id: str) -> Response:
    """Start the notebook pod for an experiment."""
    schema = NotebookSchema()
    experiment: Experiment = Experiment.query.get_or_404(
        experiment_id, description=f"Experiment {experiment_id} not found"
    )
    notebook = experiment.notebook
    notebook.start()
    db.session.commit()
    return ApiResponse.success(schema.dump(notebook), HTTPStatus.CREATED)


@notebook_bp.route("", methods=["DELETE"])
@handle_exceptions()
def stop_notebook(experiment_id: str) -> Response:
    """Stop the notebook pod for an experiment."""
    experiment: Experiment = Experiment.query.get_or_404(
        experiment_id, description=f"Experiment {experiment_id} not found"
    )
    notebook = experiment.notebook
    notebook.stop()
    return ApiResponse.success(status=HTTPStatus.NO_CONTENT)
