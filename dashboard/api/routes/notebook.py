from http import HTTPStatus

from api_response import ApiResponse
from config import API_PREFIX, GPU_TYPE, get_tier_resources
from decorators import handle_exceptions
from enums import NotebookTier
from extensions import db
from flask import Blueprint, Response, request
from models import Experiment
from schemas import NotebookSchema

notebook_bp = Blueprint("notebook", __name__, url_prefix=f"{API_PREFIX}/experiments/<experiment_id>/notebook")
notebook_config_bp = Blueprint("notebook_config", __name__, url_prefix=API_PREFIX)


@notebook_config_bp.route("/notebook-config", methods=["GET"])
@handle_exceptions()
def get_notebook_config() -> Response:
    """
    Get available notebook resource tiers and GPU availability.

    Returns:
        Response: JSON response with tiers list, default tier, and GPU availability flag.
    """
    tiers = []
    for t in NotebookTier:
        nb_res, _ = get_tier_resources(t)
        tiers.append({
            "value": t.value,
            "cpuLimit": nb_res["limits"]["cpu"],
            "memoryLimit": nb_res["limits"]["memory"],
        })
    return ApiResponse.success({
        "tiers": tiers,
        "defaultTier": NotebookTier.SMALL.value,
        "gpuAvailable": bool(GPU_TYPE),
    })


@notebook_bp.route("", methods=["GET"])
@handle_exceptions()
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
    return ApiResponse.success(schema.dump(experiment.notebook))


@notebook_bp.route("", methods=["POST"])
@handle_exceptions(rollback=True)
def start_notebook(experiment_id: str) -> Response:
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

    body = request.get_json(silent=True) or {}
    tier_str = body.get("tier")
    tier = NotebookTier(tier_str) if tier_str else None
    gpu = bool(body.get("gpu", False))

    notebook = experiment.notebook
    notebook.start(tier=tier, gpu=gpu)
    db.session.commit()
    return ApiResponse.success(schema.dump(notebook), HTTPStatus.CREATED)


@notebook_bp.route("", methods=["DELETE"])
@handle_exceptions()
def stop_notebook(experiment_id: str) -> Response:
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
    return ApiResponse.success(status=HTTPStatus.NO_CONTENT)
