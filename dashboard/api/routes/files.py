from dataclasses import asdict

from config import API_PREFIX, DATA_DIR
from flask import Blueprint, Response, jsonify, request, send_file
from utils import file_download_url, get_files_with_extensions
from validators import check_experiment_id, check_path
from werkzeug.exceptions import NotFound

files_bp = Blueprint("files", __name__, url_prefix=f"{API_PREFIX}/experiments/<experiment_id>/files")


@files_bp.route("", methods=["GET"])
def get_files(experiment_id: str) -> Response:
    """
    List files in an experiment directory, optionally filtered by extension.

    Returns:
        Response: JSON response with the list of files and their download URLs.
    """
    check_experiment_id(experiment_id)
    ext_param = request.args.get("ext", "").lower()
    extensions = [ext.strip() for ext in ext_param.split(",") if ext.strip()] if ext_param else None

    files = get_files_with_extensions(DATA_DIR / experiment_id, extensions)

    file_dicts = []
    for f in files:
        file_dict = asdict(f)
        file_dict["url"] = file_download_url(experiment_id, f.path)
        file_dicts.append(file_dict)

    return jsonify(file_dicts)


@files_bp.route("/<path:path>", methods=["GET"])
def get_file(experiment_id: str, path: str) -> Response:
    """
    Download a file from an experiment directory.

    Returns:
        Response: The file contents as an inline response, or a JSON error if the file does not exist.

    Raises:
        NotFound: If the requested file does not exist.
    """
    check_experiment_id(experiment_id)
    check_path(path, DATA_DIR / experiment_id)
    file_path = DATA_DIR / experiment_id / path

    if not file_path.exists():
        raise NotFound(f"File {path} does not exist.")

    return send_file(file_path, as_attachment=False)
