from flask import Blueprint, Response

from config import API_PREFIX, NAMESPACE
from api_response import ApiResponse
from clients import k8s


misc_bp = Blueprint(
    'misc',
    __name__,
    url_prefix=API_PREFIX
)


@misc_bp.route('/', methods=['GET'])
def index() -> Response:
    return ApiResponse.success('API is running!')


@misc_bp.route('/metrics', methods=['GET'])
def get_metrics() -> Response:
    try:
        metrics = k8s.get_namespace_resource_allocation(NAMESPACE)
        return ApiResponse.success(metrics)
    except Exception as e:
        return ApiResponse.error(e)
