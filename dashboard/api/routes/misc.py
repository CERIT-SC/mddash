from cache import metrics_cache
from config import API_PREFIX, CPU_REQUEST_QUOTA, DATA_DIR, MEMORY_REQUEST_QUOTA, PVC_SIZE
from decorators import handle_exceptions
from flask import Blueprint, Response, jsonify
from notebook_modules import load_catalog
from utils import get_du_size

misc_bp = Blueprint("misc", __name__, url_prefix=API_PREFIX)


@misc_bp.route("/", methods=["GET"])
@misc_bp.route("/health", methods=["GET"])
@handle_exceptions()
def index() -> Response:
    """
    Health check endpoint.

    Returns:
        Response: JSON response confirming the API is running.
    """
    return jsonify("API is up!")


@misc_bp.route("/notebook-modules", methods=["GET"])
@handle_exceptions()
def get_notebook_modules() -> Response:
    """
    Return curated notebook module display metadata (no internal paths or URLs).

    Returns:
        JSON response with the list of curated notebook modules.
    """
    catalog = load_catalog()
    return jsonify(catalog.to_public())


@misc_bp.route("/metrics", methods=["GET"])
@handle_exceptions()
def get_metrics() -> Response:
    """
    Get resource usage metrics for the current user.

    Returns:
        Response: JSON response with current resource requests and configured limits for CPU, memory, and storage.
    """
    from clients import k8s  # ruff:ignore[import-outside-top-level]

    if "pod_resources" in metrics_cache:
        pod_requests = metrics_cache["pod_resources"]
    else:
        pod_requests = k8s.get_pod_resource_requests()
        metrics_cache["pod_resources"] = pod_requests

    requests: dict[str, int | None] = {**pod_requests, "storage": get_du_size(DATA_DIR)}

    limits = {
        "cpu": k8s.parse_cpu(CPU_REQUEST_QUOTA),
        "memory": k8s.parse_memory(MEMORY_REQUEST_QUOTA),
        "storage": k8s.parse_memory(PVC_SIZE),
    }

    return jsonify({"requests": requests, "limits": limits})
