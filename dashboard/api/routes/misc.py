from api_response import ApiResponse
from cache import metrics_cache
from clients import k8s
from config import API_PREFIX, CPU_REQUEST_QUOTA, DATA_DIR, GPU_TYPE, MEMORY_REQUEST_QUOTA, NOTEBOOK_GPU_COUNT, PVC_SIZE
from decorators import handle_exceptions
from enums import NotebookTier
from flask import Blueprint, Response
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
    return ApiResponse.success("API is up!")


@misc_bp.route("/metrics", methods=["GET"])
@handle_exceptions()
def get_metrics() -> Response:
    """
    Get resource usage metrics for the current user.

    Returns:
        Response: JSON response with current resource requests and configured limits for CPU, memory, and storage.
    """
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

    return ApiResponse.success({"requests": requests, "limits": limits})


@misc_bp.route("/notebook-config", methods=["GET"])
@handle_exceptions()
def get_notebook_config() -> Response:
    """
    Get available notebook resource tiers and GPU availability.

    Returns:
        Response: JSON response with tiers list, default tier, and GPU availability flag.
    """
    return ApiResponse.success({
        "tiers": [t.value for t in NotebookTier],
        "defaultTier": NotebookTier.SMALL.value,
        "gpuAvailable": bool(GPU_TYPE) and NOTEBOOK_GPU_COUNT > 0,
    })
