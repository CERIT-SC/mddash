from http import HTTPStatus

from config import API_PREFIX
from decorators import handle_exceptions
from flask import Blueprint, Response, jsonify, request
from flask.typing import ResponseReturnValue
from models import (
    get_simulation,
    list_simulations,
    update_simulation,
    write_simulation,
)
from werkzeug.exceptions import BadRequest

simulations_bp = Blueprint("simulations", __name__, url_prefix=f"{API_PREFIX}/experiments/<experiment_id>/simulations")


@simulations_bp.route("", methods=["GET"])
@handle_exceptions()
def list_simulations_route(experiment_id: str) -> Response:
    """
    List all simulations for an experiment.

    Returns:
        Response: JSON response with the list of simulations.
    """
    return jsonify(list_simulations(experiment_id))


@simulations_bp.route("/<path:simulation_path>", methods=["GET"])
@handle_exceptions()
def get_simulation_route(experiment_id: str, simulation_path: str) -> Response:
    """
    Get a single simulation by its experiment-relative path.

    Returns:
        Response: JSON response with the simulation data.
    """
    return jsonify(get_simulation(experiment_id, simulation_path))


@simulations_bp.route("", methods=["POST"])
@handle_exceptions(rollback=True)
def create_simulation_route(experiment_id: str) -> ResponseReturnValue:
    """
    Create a new simulation manifest.

    Returns:
        Response: JSON response with the created simulation.

    Raises:
        BadRequest: If the body is invalid or the simulation is locked.
    """
    data = request.get_json()
    if not isinstance(data, dict):
        raise BadRequest("Request body must be a JSON object.")
    simulation = write_simulation(experiment_id, data)
    return jsonify(simulation), HTTPStatus.CREATED


@simulations_bp.route("/<path:simulation_path>", methods=["PATCH"])
@handle_exceptions(rollback=True)
def update_simulation_route(experiment_id: str, simulation_path: str) -> ResponseReturnValue:
    """
    Edit an unlocked simulation manifest.

    Returns:
        Response: JSON response with the updated simulation.

    Raises:
        BadRequest: If the body is not a JSON object.
    """
    data = request.get_json()
    if not isinstance(data, dict):
        raise BadRequest("Request body must be a JSON object.")
    simulation = update_simulation(experiment_id, simulation_path, data)
    return jsonify(simulation)
