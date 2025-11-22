from http import HTTPStatus
from flask import Blueprint, Response, request, send_file

from config import API_PREFIX, DATA_DIR
from api_response import ApiResponse
from utils import get_files_with_extensions, check_experiment_id, check_path
from decorators import handle_exceptions


files_bp = Blueprint(
    'files',
    __name__,
    url_prefix=f'{API_PREFIX}/experiments/<experiment_id>/files'
)


@files_bp.route('', methods=['GET'])
@handle_exceptions()
def get_files(experiment_id: str) -> Response:
    check_experiment_id(experiment_id)
    ext_param = request.args.get('ext', '').lower()
    extensions = [ext.strip() for ext in ext_param.split(',') if ext.strip()] if ext_param else None

    files = get_files_with_extensions(DATA_DIR / experiment_id, extensions)

    for f in files:
        f['url'] = f'{API_PREFIX}/experiments/{experiment_id}/files/{f["name"]}'

    return ApiResponse.success(files)


@files_bp.route('/<path:path>', methods=['GET'])
@handle_exceptions()
def get_file(experiment_id: str, path: str) -> Response:
    check_experiment_id(experiment_id)
    check_path(path, DATA_DIR / experiment_id)
    file_path = DATA_DIR / experiment_id / path

    if not file_path.exists():
        return ApiResponse.error(f'File {path} does not exist.', HTTPStatus.NOT_FOUND)

    return send_file(file_path, as_attachment=False)
