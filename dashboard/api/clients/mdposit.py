"""MDPosit/MDDB REST client."""

import logging
from http import HTTPStatus
from pathlib import Path
from urllib.parse import quote, urlparse

import anyio
from core.config import MDPOSIT_HOST, MDPOSIT_REST_URL, MDPOSIT_TRUSTED_PARENT_HOST

from clients.http import client

logger = logging.getLogger(__name__)

DOWNLOAD_CHUNK_BYTES = 128 * 1024


def _api_url(path: str) -> str:
    return f"{MDPOSIT_REST_URL.rstrip('/')}/{path.lstrip('/')}"


def _project_url(accession: str, suffix: str = "") -> str:
    path = f"projects/{accession}"
    if suffix:
        path = f"{path}/{suffix.strip('/')}"
    return _api_url(path)


async def get_project(accession: str) -> dict:
    """
    Fetch project metadata from MDPosit.

    Raises:
        ValueError: If the project does not exist.
    """
    response = await client().get(_project_url(accession), timeout=30)
    if response.status_code == HTTPStatus.NOT_FOUND:
        raise ValueError(f"Project {accession} not found on MDPosit")
    response.raise_for_status()
    return response.json()


async def list_files(accession: str) -> list[str]:
    """File names available for download in an MDPosit project."""
    response = await client().get(_project_url(accession, "files"), timeout=30)
    if response.status_code == HTTPStatus.NOT_FOUND:
        return []
    response.raise_for_status()
    data = response.json()
    if not isinstance(data, list):
        return []
    return [item["name"] if isinstance(item, dict) else str(item) for item in data]


async def download_file(accession: str, filename: str, output_dir: Path) -> Path:
    """
    Download a project file from MDPosit into `output_dir`.

    Raises:
        ValueError: If the file name attempts path traversal.
    """
    filename_path = Path(filename)
    parts = [part for part in filename_path.parts if part not in {"", "."}]
    if ".." in parts or filename_path.is_absolute():
        raise ValueError(f"Invalid MDPosit file path: {filename}")

    quoted_filename = "/".join(quote(part) for part in parts)
    output_path = anyio.Path(output_dir / filename_path)
    async with client().stream("GET", _project_url(accession, f"files/{quoted_filename}"), timeout=300) as response:
        response.raise_for_status()
        await output_path.parent.mkdir(parents=True, exist_ok=True)
        async with await anyio.open_file(output_path, "wb") as output_file:
            async for chunk in response.aiter_bytes(DOWNLOAD_CHUNK_BYTES):
                await output_file.write(chunk)

    return Path(output_path)


async def download_project(accession: str, output_dir: Path) -> list[Path]:
    """
    Download all files of an MDPosit project.

    Raises:
        ValueError: If no files are found for the project.
    """
    await anyio.Path(output_dir).mkdir(parents=True, exist_ok=True)
    filenames = await list_files(accession)
    if not filenames:
        raise ValueError(f"No files found for project {accession}")

    downloaded_paths = []
    for filename in filenames:
        logger.info("Downloading MDPosit file '%s' for project %s", filename, accession)
        downloaded_paths.append(await download_file(accession, filename, output_dir))
    return downloaded_paths


def trusted_hosts() -> list[str]:
    """Trusted MDPosit host names."""
    return [host for host in [MDPOSIT_TRUSTED_PARENT_HOST, MDPOSIT_HOST] if host]


def is_mdposit_url(url: str, hosts: list[str] | None = None) -> bool:
    """Whether the URL hostname exactly matches a trusted MDPosit host."""
    hostname = urlparse(url).hostname
    if hostname is None:
        return False
    trusted = hosts if hosts is not None else trusted_hosts()
    return hostname.lower() in {host.lower() for host in trusted}


def extract_accession(url: str) -> str:
    """MDPosit project accession from a UI or API URL, or an empty string."""
    parsed = urlparse(url)
    path_segments = [s for s in parsed.path.split("/") if s]
    # MDPosit UI uses hash routing, so the accession lives in the fragment (#/id/{accession}/...).
    source = parsed.fragment if not path_segments else parsed.path
    segments = [s for s in source.split("/") if s]
    if "id" in segments:
        index = segments.index("id")
        return segments[index + 1] if index + 1 < len(segments) else ""
    return segments[-1] if segments else ""
