from http import HTTPStatus

from config import API_PREFIX
from enums import NotebookTier
from extensions import db
from flask import Blueprint, Response, jsonify, request
from flask.typing import ResponseReturnValue
from models import Experiment
from models.notebook import get_tier_resources
from schemas import NotebookSchema, StartNotebookSchema

notebook_bp = Blueprint("notebook", __name__, url_prefix=f"{API_PREFIX}/experiments/<experiment_id>/notebook")
notebook_config_bp = Blueprint("notebook_config", __name__, url_prefix=API_PREFIX)


@notebook_config_bp.route("/notebook-config", methods=["GET"])
def get_notebook_config() -> Response:
    """
    Get available notebook resource tiers and the default tier.

    Returns:
        Response: JSON response with tiers list and default tier.
    """
    tiers = []
    for t in NotebookTier:
        nb_res = get_tier_resources(t)
        tiers.append({
            "value": t.value,
            "cpuLimit": nb_res["limits"]["cpu"],
            "memoryLimit": nb_res["limits"]["memory"],
        })
    return jsonify({
        "tiers": tiers,
        "defaultTier": NotebookTier.SMALL.value,
    })


@notebook_bp.route("", methods=["GET"])
def get_notebook(experiment_id: str) -> Response:
    """
    Get the notebook instance for an experiment.

    Returns:
        Response: JSON response with the notebook data.
    """
    schema = NotebookSchema()
    experiment: Experiment = Experiment.query.get_or_404(
        experiment_id, description=f"Experiment {experiment_id} not found"
    )
    return jsonify(schema.dump(experiment.notebook))


@notebook_bp.route("", methods=["POST"])
def start_notebook(experiment_id: str) -> ResponseReturnValue:
    """
    Start the notebook pod for an experiment.

    Accepts optional JSON body with ``tier`` (e.g. "1x", "2x", "4x") and ``gpu`` (boolean).

    Returns:
        Response: JSON response with the started notebook data.
    """
    schema = NotebookSchema()
    experiment: Experiment = Experiment.query.get_or_404(
        experiment_id, description=f"Experiment {experiment_id} not found"
    )

    data = StartNotebookSchema().load(request.get_json(silent=True) or {})
    notebook = experiment.notebook
    notebook.start(tier=data["tier"], gpu=data["gpu"])
    db.session.commit()
    return jsonify(schema.dump(notebook)), HTTPStatus.CREATED


@notebook_bp.route("", methods=["DELETE"])
def stop_notebook(experiment_id: str) -> ResponseReturnValue:
    """
    Stop the notebook pod for an experiment.

    Returns:
        Response: Empty JSON response with 204 No Content on success.
    """
    experiment: Experiment = Experiment.query.get_or_404(
        experiment_id, description=f"Experiment {experiment_id} not found"
    )
    notebook = experiment.notebook
    notebook.stop()
    return "", HTTPStatus.NO_CONTENT
