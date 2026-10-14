import mimetypes
from typing import Annotated

import anyio
from config import API_PREFIX, DATA_DIR
from errors import NotFound
from fastapi import APIRouter, Path, Query
from fastapi.responses import FileResponse
from schemas.common import FileInfo
from utils import file_download_url, get_files_with_extensions
from validators import check_experiment_id, check_path

from routes._responses import problems

router = APIRouter(prefix=f"{API_PREFIX}/experiments/{{experiment_id}}/files", tags=["Files"])


@router.get(
    "",
    summary="List experiment files",
    operation_id="listExperimentFiles",
    response_description="Files",
    responses=problems(400),
)
async def list_files(
    experiment_id: Annotated[str, Path(min_length=1)],
    ext: Annotated[str | None, Query(description="Comma-separated file extensions")] = None,
) -> list[FileInfo]:
    """List files in an experiment directory, optionally filtered by extension."""
    check_experiment_id(experiment_id)
    extensions = [e.strip() for e in ext.lower().split(",") if e.strip()] if ext else None
    files = await anyio.to_thread.run_sync(get_files_with_extensions, DATA_DIR / experiment_id, extensions)
    return [
        {"name": f.name, "size": f.size, "path": f.path, "url": file_download_url(experiment_id, f.path)} for f in files
    ]


@router.get(
    "/{path:path}",
    summary="Download an experiment file",
    operation_id="downloadExperimentFile",
    response_class=FileResponse,
    responses={
        200: {
            "description": "File contents; the actual media type is inferred from the file",
            "content": {
                "application/octet-stream": {
                    "schema": {"type": "string", "contentMediaType": "application/octet-stream"}
                }
            },
        },
        **problems(400, 404),
    },
)
async def download(
    experiment_id: Annotated[str, Path(min_length=1)], path: Annotated[str, Path(min_length=1)]
) -> FileResponse:
    """
    Serve a file from an experiment directory inline.

    Raises:
        NotFound: If the requested file does not exist.
    """
    check_experiment_id(experiment_id)
    check_path(path, DATA_DIR / experiment_id)
    file_path = DATA_DIR / experiment_id / path
    if not await anyio.Path(file_path).is_file():
        raise NotFound(f"File {path} does not exist.")
    media_type = mimetypes.guess_type(file_path.name)[0] or "application/octet-stream"
    return FileResponse(file_path, media_type=media_type)
