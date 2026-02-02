from http import HTTPStatus

from api_response import ApiResponse
from config import API_PREFIX, DEFAULT_NOTEBOOKS_REPO
from decorators import handle_exceptions
from extensions import db
from flask import Blueprint, Response, request, session
from models import Experiment
from schemas import ExperimentSchema
from token_manager import MDRepoTokenManager
from utils import validate_git_url

experiments_bp = Blueprint("experiments", __name__, url_prefix=f"{API_PREFIX}/experiments")


@experiments_bp.route("", methods=["GET"])
@handle_exceptions()
def list_experiments() -> Response:
    """List all experiments."""
    experiments: list[Experiment] = Experiment.query.all()
    schema = ExperimentSchema(many=True)
    return ApiResponse.success(schema.dump(experiments))


@experiments_bp.route("", methods=["POST"])
@handle_exceptions(rollback=True)
def create_experiment() -> Response:
    """Create a new experiment from PDB, repository URL, or uploaded files."""
    schema = ExperimentSchema()
    form = request.form

    name = form["experiment-name"]
    pdb_id = form.get("pdb-id")
    repo_url = form.get("repo-url")
    notebooks_repo = form.get("notebooks-repo", DEFAULT_NOTEBOOKS_REPO)
    simulation_files = request.files.getlist("simulation-files")

    validate_git_url(notebooks_repo)

    match form["type"]:
        case "pdb" if pdb_id:
            experiment = Experiment.from_pdb(name, pdb_id, notebooks_repo)
        case "repo" if repo_url:
            experiment = Experiment.from_repo(name, repo_url, notebooks_repo)
        case "file" if simulation_files:
            experiment = Experiment.from_files(name, simulation_files, notebooks_repo)
        case _:
            return ApiResponse.error("Invalid experiment type or missing data.", HTTPStatus.BAD_REQUEST)

    db.session.add(experiment)
    db.session.commit()
    return ApiResponse.success(schema.dump(experiment), HTTPStatus.CREATED)


@experiments_bp.route("/<experiment_id>", methods=["GET"])
@handle_exceptions()
def get_experiment(experiment_id: str) -> Response:
    """Get an experiment by ID."""
    experiment: Experiment = Experiment.query.get_or_404(
        experiment_id, description=f"Experiment {experiment_id} not found"
    )
    schema = ExperimentSchema()
    return ApiResponse.success(schema.dump(experiment))


@experiments_bp.route("/<experiment_id>", methods=["DELETE"])
@handle_exceptions(rollback=True)
def delete_experiment(experiment_id: str) -> Response:
    """Delete an experiment and all associated resources."""
    experiment: Experiment = Experiment.query.get_or_404(
        experiment_id, description=f"Experiment {experiment_id} not found"
    )
    experiment.delete()
    db.session.delete(experiment)
    db.session.commit()
    return ApiResponse.success(status=HTTPStatus.NO_CONTENT)


@experiments_bp.route("/<experiment_id>", methods=["PATCH"])
@handle_exceptions(rollback=True)
def edit_experiment(experiment_id: str) -> Response:
    """Update experiment properties."""
    experiment: Experiment = Experiment.query.get_or_404(
        experiment_id, description=f"Experiment {experiment_id} not found"
    )
    data = request.get_json()
    if not data:
        return ApiResponse.error("No data provided.", HTTPStatus.BAD_REQUEST)

    updated = False
    # Currently only name can be edited
    if "name" in data:
        experiment.name = data["name"]
        updated = True

    if not updated:
        return ApiResponse.error("No valid fields to update.", HTTPStatus.BAD_REQUEST)

    db.session.commit()
    schema = ExperimentSchema()
    return ApiResponse.success(schema.dump(experiment))


@experiments_bp.route("/<experiment_id>/publish", methods=["POST"])
@handle_exceptions(rollback=True)
def publish_experiment(experiment_id: str) -> Response:
    """Publish experiment to MDRepo. Requires MDRepo OAuth authentication."""
    experiment: Experiment = Experiment.query.get_or_404(
        experiment_id, description=f"Experiment {experiment_id} not found"
    )

    # Check if user is authenticated with MDRepo and has a valid token
    token_manager = MDRepoTokenManager(session)
    token = token_manager.get_valid_token()
    if not token:
        return ApiResponse.error("Not authenticated with MDRepo. Please authenticate first.", HTTPStatus.UNAUTHORIZED)

    # TODO: Add endpoint to fetch available communities from MDRepo and allow user to select from a dropdown in the publish UI.
    #       Pass the selected community to this endpoint and use it when publishing the experiment instead of hardcoding 'ceitec'.
    mdrepo_experiment = experiment.publish(community="ceitec")

    return ApiResponse.success(mdrepo_experiment, HTTPStatus.CREATED)


@experiments_bp.route("/<experiment_id>/step", methods=["GET"])
@handle_exceptions()
def get_experiment_step(experiment_id: str) -> Response:
    """Get the current workflow step for an experiment."""
    experiment: Experiment = Experiment.query.get_or_404(
        experiment_id, description=f"Experiment {experiment_id} not found"
    )
    return ApiResponse.success(experiment.step)
