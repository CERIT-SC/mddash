from flask import Blueprint, Response

from config import API_PREFIX, DATA_DIR, CPU_REQUEST_QUOTA, MEMORY_REQUEST_QUOTA, PVC_SIZE
from api_response import ApiResponse
from clients import k8s
from decorators import handle_exceptions
from utils import get_directory_size


misc_bp = Blueprint(
    'misc',
    __name__,
    url_prefix=API_PREFIX
)


@misc_bp.route('/', methods=['GET'])
@misc_bp.route('/health', methods=['GET'])
@handle_exceptions()
def index() -> Response:
    return ApiResponse.success('API is up!')


@misc_bp.route('/metrics', methods=['GET'])
@handle_exceptions()
def get_metrics() -> Response:
    # Get actual pod resource requests
    requests = k8s.get_pod_resource_requests()

    # Calculate storage used in DATA_DIR
    requests['storage'] = get_directory_size(DATA_DIR)

    limits = {
        'cpu': k8s._parse_cpu(CPU_REQUEST_QUOTA),
        'memory': k8s._parse_memory(MEMORY_REQUEST_QUOTA),
        'storage': k8s._parse_memory(PVC_SIZE)
    }

    return ApiResponse.success({
        'requests': requests,
        'limits': limits
    })
