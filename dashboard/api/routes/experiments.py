from http import HTTPStatus

from config import API_PREFIX, DEFAULT_NOTEBOOKS_REPO
from decorators import handle_exceptions
from enums import Engine
from extensions import db
from flask import Blueprint, Response, jsonify, request, session
from flask.typing import ResponseReturnValue
from models import Experiment
from notebook_modules import load_catalog
from schemas import ExperimentSchema
from token_manager import MDRepoTokenManager
from validators import validate_git_url
from werkzeug.exceptions import BadRequest, Unauthorized

experiments_bp = Blueprint("experiments", __name__, url_prefix=f"{API_PREFIX}/experiments")


@experiments_bp.route("", methods=["GET"])
@handle_exceptions()
def list_experiments() -> Response:
    """
    List all experiments.

    Returns:
        Response: JSON response with the list of all experiments.
    """
    experiments: list[Experiment] = Experiment.query.all()
    schema = ExperimentSchema(many=True)
    return jsonify(schema.dump(experiments))


@experiments_bp.route("", methods=["POST"])
@handle_exceptions(rollback=True)
def create_experiment() -> ResponseReturnValue:
    """
    Create a new experiment from PDB, repository URL, or uploaded files.

    Returns:
        Response: JSON response with the created experiment on success, or an error response for invalid input.

    Raises:
        BadRequest: If the experiment type or data is invalid.
    """
    schema = ExperimentSchema()
    form = request.form

    name = form["experiment-name"]
    pdb_source = form.get("pdb")
    repo_url = form.get("repo-url")
    notebooks_repo = form.get("notebooks-repo", DEFAULT_NOTEBOOKS_REPO)
    access_token = form.get("access-token")
    notebook_module_id = form.get("notebook-module") or None
    simulation_files = request.files.getlist("simulation-files")

    # Get engine from form, default to GMX
    engine_str = form.get("engine", "GMX")
    try:
        engine = Engine.from_string(engine_str)
    except ValueError:
        raise BadRequest(f"Invalid engine: {engine_str}")

    if notebook_module_id is not None:
        # Curated mode: resolve the module from the bundled catalog and use its
        # configured repository (defaults to the platform default). No
        # client-provided repository URL or path is trusted.
        module = load_catalog().get_module_for_engine(notebook_module_id, engine.value)
        if module is None:
            raise BadRequest(f"Unknown or incompatible notebook module: {notebook_module_id}")
        notebooks_repo = module.repository or DEFAULT_NOTEBOOKS_REPO
    else:
        # Custom mode: validate the client-provided repository URL.
        validate_git_url(notebooks_repo)

    match form["type"]:
        case "pdb" if pdb_source:
            experiment = Experiment.from_pdb(
                name, pdb_source, notebooks_repo, access_token, engine=engine, notebook_module_id=notebook_module_id
            )
        case "repo" if repo_url:
            experiment = Experiment.from_repo(
                name, repo_url, notebooks_repo, access_token, engine=engine, notebook_module_id=notebook_module_id
            )
        case "file" if simulation_files:
            experiment = Experiment.from_files(
                name,
                simulation_files,
                notebooks_repo,
                access_token,
                engine=engine,
                notebook_module_id=notebook_module_id,
            )
        case _:
            raise BadRequest("Invalid experiment type or missing data.")

    db.session.add(experiment)
    db.session.commit()
    return jsonify(schema.dump(experiment)), HTTPStatus.CREATED


@experiments_bp.route("/<experiment_id>", methods=["GET"])
@handle_exceptions()
def get_experiment(experiment_id: str) -> Response:
    """
    Get an experiment by ID.

    Returns:
        Response: JSON response with the experiment data.
    """
    experiment: Experiment = Experiment.query.get_or_404(
        experiment_id, description=f"Experiment {experiment_id} not found"
    )
    schema = ExperimentSchema()
    return jsonify(schema.dump(experiment))


@experiments_bp.route("/<experiment_id>", methods=["DELETE"])
@handle_exceptions(rollback=True)
def delete_experiment(experiment_id: str) -> ResponseReturnValue:
    """
    Delete an experiment and all associated resources.

    Returns:
        Response: Empty JSON response with 204 No Content on success.
    """
    experiment: Experiment = Experiment.query.get_or_404(
        experiment_id, description=f"Experiment {experiment_id} not found"
    )
    experiment.delete()
    db.session.delete(experiment)
    db.session.commit()
    return "", HTTPStatus.NO_CONTENT


@experiments_bp.route("/<experiment_id>", methods=["PATCH"])
@handle_exceptions(rollback=True)
def edit_experiment(experiment_id: str) -> Response:
    """
    Update experiment properties.

    Returns:
        Response: JSON response with the updated experiment data, or an error response for invalid input.

    Raises:
        BadRequest: If no valid fields are provided for update.
    """
    experiment: Experiment = Experiment.query.get_or_404(
        experiment_id, description=f"Experiment {experiment_id} not found"
    )
    data = request.get_json()
    if not data:
        raise BadRequest("No data provided.")

    updated = False
    # Currently only name can be edited
    if "name" in data:
        experiment.name = data["name"]
        updated = True

    if not updated:
        raise BadRequest("No valid fields to update.")

    db.session.commit()
    schema = ExperimentSchema()
    return jsonify(schema.dump(experiment))


@experiments_bp.route("/<experiment_id>/publish", methods=["POST"])
@handle_exceptions(rollback=True)
def publish_experiment(experiment_id: str) -> ResponseReturnValue:
    """
    Publish experiment to the requested target.

    Returns:
        Response: JSON response with the publication metadata.

    Raises:
        BadRequest: If the publish target or selected files are invalid.
        Unauthorized: If the user is not authenticated with MDRepo for Invenio publishing.
    """
    experiment: Experiment = Experiment.query.get_or_404(
        experiment_id, description=f"Experiment {experiment_id} not found"
    )
    if request.get_data(cache=True):
        if not request.is_json:
            raise BadRequest("Publish request body must be JSON.")
        data = request.get_json()
        if not isinstance(data, dict):
            raise BadRequest("Publish request body must be a JSON object.")
    else:
        data = {}

    target = data.get("target", "invenio")
    if not isinstance(target, str):
        raise BadRequest("Publish target must be a string.")

    if target == "invenio":
        token_manager = MDRepoTokenManager(session)
        token = token_manager.get_valid_token()
        if not token:
            raise Unauthorized("Not authenticated with MDRepo. Please authenticate first.")

        # TODO: Add endpoint to fetch available communities from MDRepo and allow user to select from a dropdown in the publish UI.
        #       Pass the selected community to this endpoint and use it when publishing the experiment instead of hardcoding 'ceitec'.
        result = experiment.publish(target="invenio", community="ceitec")
    elif target == "mdposit":
        simulation_path = data.get("simulation_path")
        if not isinstance(simulation_path, str) or not simulation_path:
            raise BadRequest("MDPosit publish requires simulation_path.")

        result = experiment.publish(target="mdposit", simulation_path=simulation_path)
    else:
        raise BadRequest(f"Unknown publish target: {target}")

    return jsonify(result), HTTPStatus.CREATED


@experiments_bp.route("/<experiment_id>/step", methods=["GET"])
@handle_exceptions()
def get_experiment_step(experiment_id: str) -> Response:
    """
    Get the current workflow step for an experiment.

    Returns:
        Response: JSON response with the current workflow step value.
    """
    experiment: Experiment = Experiment.query.get_or_404(
        experiment_id, description=f"Experiment {experiment_id} not found"
    )
    return jsonify(experiment.step)
