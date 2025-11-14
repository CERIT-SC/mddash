from flask import Blueprint, Response

from config import API_PREFIX, DATA_DIR
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
    metrics = k8s.get_namespace_resource_allocation()

    # Add storage usage and capacity
    metrics['requests']['storage'] = get_directory_size(DATA_DIR)
    metrics['limits']['storage'] = k8s.get_pvc_storage_capacity()

    return ApiResponse.success(metrics)
