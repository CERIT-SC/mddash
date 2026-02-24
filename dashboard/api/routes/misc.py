from api_response import ApiResponse
from cache import metrics_cache
from clients import k8s
from config import API_PREFIX, CPU_REQUEST_QUOTA, DATA_DIR, MEMORY_REQUEST_QUOTA, PVC_SIZE
from decorators import handle_exceptions
from flask import Blueprint, Response
from utils import duc_query_size

misc_bp = Blueprint("misc", __name__, url_prefix=API_PREFIX)


@misc_bp.route("/", methods=["GET"])
@misc_bp.route("/health", methods=["GET"])
@handle_exceptions()
def index() -> Response:
    """Health check endpoint."""
    return ApiResponse.success("API is up!")


@misc_bp.route("/metrics", methods=["GET"])
@handle_exceptions()
def get_metrics() -> Response:
    """Get resource usage metrics for the current user."""
    if "pod_resources" in metrics_cache:
        requests = metrics_cache["pod_resources"]
    else:
        requests = k8s.get_pod_resource_requests()
        metrics_cache["pod_resources"] = requests

    requests["storage"] = duc_query_size(DATA_DIR)

    limits = {
        "cpu": k8s.parse_cpu(CPU_REQUEST_QUOTA),
        "memory": k8s.parse_memory(MEMORY_REQUEST_QUOTA),
        "storage": k8s.parse_memory(PVC_SIZE),
    }

    return ApiResponse.success({"requests": requests, "limits": limits})
