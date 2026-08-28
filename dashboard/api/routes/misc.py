import time

from config import API_PREFIX, DATA_DIR, PVC_SIZE
from flask import Blueprint, Response, jsonify
from notebook_modules import load_catalog
from utils import get_du_size

misc_bp = Blueprint("misc", __name__, url_prefix=API_PREFIX)

# The API sidecar starts with the user server pod, so process uptime ≈ server uptime.
_STARTED_AT = time.monotonic()


@misc_bp.route("/", methods=["GET"])
@misc_bp.route("/health", methods=["GET"])
def index() -> Response:
    """
    Health check endpoint.

    Returns:
        Response: JSON response confirming the API is running.
    """
    return jsonify("API is up!")


@misc_bp.route("/notebook-modules", methods=["GET"])
def get_notebook_modules() -> Response:
    """
    Return curated notebook module display metadata (no internal paths or URLs).

    Returns:
        JSON response with the list of curated notebook modules.
    """
    catalog = load_catalog()
    return jsonify(catalog.to_public())


@misc_bp.route("/metrics", methods=["GET"])
def get_metrics() -> Response:
    """
    Get storage usage and server uptime for the current user.

    Returns:
        Response: JSON response with used/limit storage in bytes (used is null
        until the du monitor records a measurement) and the server uptime in seconds.
    """
    from clients import k8s  # ruff:ignore[import-outside-top-level]

    return jsonify({
        "storage_used_bytes": get_du_size(DATA_DIR),
        "storage_limit_bytes": k8s.parse_memory(PVC_SIZE),
        "uptime_seconds": round(time.monotonic() - _STARTED_AT),
    })
