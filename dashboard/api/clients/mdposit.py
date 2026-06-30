"""MDPosit/MDDB REST client."""

import logging
from http import HTTPStatus
from pathlib import Path
from shutil import copyfileobj
from urllib.parse import quote, urlparse

import requests
from config import MDPOSIT_HOST, MDPOSIT_REST_URL, MDPOSIT_TRUSTED_PARENT_HOST

logger = logging.getLogger(__name__)


def _api_url(path: str) -> str:
    """
    Build an MDPosit REST API URL.

    Args:
        path: API path relative to the configured REST root.

    Returns:
        Absolute API URL.
    """
    return f"{MDPOSIT_REST_URL.rstrip('/')}/{path.lstrip('/')}"


def _project_url(accession: str, suffix: str = "") -> str:
    """
    Build a project API URL.

    Args:
        accession: Project accession.
        suffix: Optional project-relative path suffix.

    Returns:
        Absolute project API URL.
    """
    path = f"projects/{accession}"
    if suffix:
        path = f"{path}/{suffix.strip('/')}"
    return _api_url(path)


def get_project(accession: str) -> dict:
    """
    Fetch project metadata from MDPosit.

    Args:
        accession: Project accession.

    Returns:
        Project metadata.

    Raises:
        ValueError: If the project does not exist.
    """
    response = requests.get(_project_url(accession), timeout=30)
    if response.status_code == HTTPStatus.NOT_FOUND:
        raise ValueError(f"Project {accession} not found on MDPosit")

    response.raise_for_status()
    return response.json()


def list_files(accession: str) -> list[str]:
    """
    List files available for an MDPosit project.

    Args:
        accession: Project accession.

    Returns:
        File names available for download.
    """
    response = requests.get(_project_url(accession, "files"), timeout=30)
    if response.status_code == HTTPStatus.NOT_FOUND:
        return []

    response.raise_for_status()
    data = response.json()
    if not isinstance(data, list):
        return []

    return [item["name"] if isinstance(item, dict) else str(item) for item in data]


def download_file(accession: str, filename: str, output_dir: Path) -> Path:
    """
    Download a project file from MDPosit.

    Args:
        accession: Project accession.
        filename: Project-relative file name.
        output_dir: Directory where the file should be saved.

    Returns:
        Path to the downloaded file.

    Raises:
        ValueError: If the file name attempts path traversal.
    """
    filename_path = Path(filename)
    parts = [part for part in filename_path.parts if part not in {"", "."}]
    if ".." in parts or filename_path.is_absolute():
        raise ValueError(f"Invalid MDPosit file path: {filename}")

    quoted_filename = "/".join(quote(part) for part in parts)
    output_path = output_dir / filename_path
    with requests.get(_project_url(accession, f"files/{quoted_filename}"), stream=True, timeout=300) as response:
        response.raise_for_status()

        output_path.parent.mkdir(parents=True, exist_ok=True)
        with output_path.open("wb") as output_file:
            copyfileobj(response.raw, output_file)

    return output_path


def download_project(accession: str, output_dir: Path) -> list[Path]:
    """
    Download all files for an MDPosit project.

    Args:
        accession: Project accession.
        output_dir: Directory where files should be saved.

    Returns:
        Paths to downloaded files.

    Raises:
        ValueError: If no files are found for the project.
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    filenames = list_files(accession)
    if not filenames:
        raise ValueError(f"No files found for project {accession}")

    downloaded_paths = []
    for filename in filenames:
        logger.info("Downloading MDPosit file '%s' for project %s", filename, accession)
        downloaded_paths.append(download_file(accession, filename, output_dir))

    return downloaded_paths


def trusted_hosts() -> list[str]:
    """
    Return trusted MDPosit host names.

    Returns:
        Configured trusted host names.
    """
    return [host for host in [MDPOSIT_TRUSTED_PARENT_HOST, MDPOSIT_HOST] if host]


def is_mdposit_url(url: str, hosts: list[str] | None = None) -> bool:
    """
    Check whether a URL belongs to a trusted MDPosit host.

    Args:
        url: URL to check.
        hosts: Optional trusted host override.

    Returns:
        True if the URL hostname exactly matches a trusted host.
    """
    hostname = urlparse(url).hostname
    if hostname is None:
        return False

    trusted = hosts if hosts is not None else trusted_hosts()
    return hostname.lower() in {host.lower() for host in trusted}


def extract_accession(url: str) -> str:
    """
    Extract the MDPosit project accession from a UI or API URL.

    Args:
        url: MDPosit project URL.

    Returns:
        The accession, or an empty string if none is found.
    """
    parsed = urlparse(url)
    path_segments = [s for s in parsed.path.split("/") if s]
    # MDPosit UI uses hash routing, so the accession lives in the fragment (#/id/{accession}/...).
    source = parsed.fragment if not path_segments else parsed.path
    segments = [s for s in source.split("/") if s]
    if "id" in segments:
        index = segments.index("id")
        return segments[index + 1] if index + 1 < len(segments) else ""
    return segments[-1] if segments else ""
