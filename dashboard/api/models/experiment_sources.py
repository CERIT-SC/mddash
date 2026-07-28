"""
Experiment source acquisition utilities.

Standalone functions for fetching, validating, and importing experiment files
from PDB IDs, direct URLs, InvenioRDM repositories, and MDPosit projects.
Used by the ``Experiment`` factory methods (``from_pdb``, ``from_repo``).
"""

from __future__ import annotations

import logging
import tempfile
import zipfile
from http import HTTPStatus
from pathlib import Path
from shutil import move
from typing import TYPE_CHECKING
from urllib.parse import urljoin, urlparse

import requests
from clients import mdposit
from config import DATA_DIR
from errors import ApiError
from validators import validate_fetch_target, validate_http_url
from werkzeug.exceptions import BadRequest, InternalServerError, NotFound

if TYPE_CHECKING:
    from .simulation import Simulation

logger = logging.getLogger(__name__)

_REDIRECT_STATUSES = {301, 302, 303, 307, 308}
_PDB_STRUCTURE_RECORDS = {"ATOM", "HETATM"}


def list_simulations(experiment_id: str) -> list["Simulation"]:
    """
    Deferred import to avoid a circular dependency with the Simulation model.

    Returns:
        List of Simulation instances.
    """
    from .simulation import Simulation  # ruff:ignore[import-outside-top-level]

    return Simulation.list(experiment_id)


def fetch_pdb(url: str, *, max_redirects: int = 5) -> requests.Response:
    """
    Fetch a PDB URL without auto-following redirects.

    Each hop is SSRF-validated to prevent internal-network access via
    redirect chains.

    Returns:
        The final non-redirect response.

    Raises:
        InternalServerError: If the redirect chain exceeds max_redirects.
    """
    for _ in range(max_redirects + 1):
        validate_fetch_target(url)
        response = requests.get(url, timeout=30, allow_redirects=False)
        if response.status_code not in _REDIRECT_STATUSES:
            return response
        location = response.headers.get("Location")
        if not location:
            return response
        url = validate_http_url(urljoin(url, location))
    raise InternalServerError(description="Too many redirects while downloading PDB file.")


def validate_pdb_content(content: bytes) -> None:
    """
    Reject downloaded content that is not a valid PDB structure file.

    Catches HTML error pages, login redirects, and binary responses that return
    200 but aren't valid PDB files — a structural file must contain at least one
    ATOM or HETATM record (columns 1-6).

    Raises:
        BadRequest: If no ATOM/HETATM record is present.
    """
    text = content.decode("utf-8", errors="replace")
    for line in text.splitlines():
        if line[:6].strip() in _PDB_STRUCTURE_RECORDS:
            return
    raise BadRequest(description="Downloaded content is not a valid PDB file (no ATOM or HETATM records).")


def resolve_repo_link(repo_link: str) -> str:
    """
    Follow DOI redirects to reach the final repository URL.

    Returns:
        The resolved URL.
    """
    resolved = repo_link.strip().rstrip("/")
    if urlparse(resolved).netloc == "doi.org":
        response = requests.head(resolved, allow_redirects=True, timeout=30)
        resolved = response.url.rstrip("/")
    return resolved


def safe_extract_zip(zf: zipfile.ZipFile, output_dir: Path) -> None:
    """
    Reject path traversal attempts (e.g. ``../../etc/passwd``) before extraction.

    Raises:
        BadRequest: If a member path escapes the output directory.
    """
    resolved_output_dir = output_dir.resolve()
    for member in zf.infolist():
        output_path = (output_dir / member.filename).resolve()
        try:
            output_path.relative_to(resolved_output_dir)
        except ValueError as exc:
            raise BadRequest(description=f"Unsafe path in repository archive: {member.filename}") from exc
        zf.extract(member, output_dir)


def import_invenio_repo(repo_link: str, experiment_id: str) -> None:
    """
    Download and extract an InvenioRDM-compatible repository (Zenodo, MDRepo, etc.).

    Raises:
        NotFound: If the repository is not found.
    """
    parsed = urlparse(repo_link)
    path_parts = [p for p in parsed.path.split("/") if p]
    record_id: str = path_parts[-1]
    records_idx: int = path_parts.index("records")  # raises ValueError if missing
    prefix_parts: list[str] = path_parts[:records_idx]
    api_segment: str = "/".join(prefix_parts) if prefix_parts else "records"
    url: str = f"{parsed.scheme}://{parsed.netloc}/api/{api_segment}/{record_id}/files-archive"

    with tempfile.NamedTemporaryFile(suffix=".zip") as tmp_file:
        tmp_path = Path(tmp_file.name)
        with requests.get(url, stream=True, timeout=300) as response:
            if response.status_code == HTTPStatus.NOT_FOUND:
                raise NotFound(description=f"Repository '{repo_link}' not found.")
            if response.status_code != HTTPStatus.OK:
                raise ApiError(
                    HTTPStatus.INTERNAL_SERVER_ERROR,
                    "Failed to download repository.",
                    "urn:mddash:upstream-download-failed",
                    "The repository couldn't be fetched; check the URL or try again in a moment.",
                )

            for chunk in response.iter_content(chunk_size=128 * 1024):
                tmp_file.write(chunk)

        tmp_file.flush()
        with zipfile.ZipFile(tmp_path) as zf:
            safe_extract_zip(zf, DATA_DIR / experiment_id)


def import_mdposit_repo(repo_link: str, experiment_id: str) -> None:
    """
    Download an MDPosit project into the experiment directory.

    Raises:
        BadRequest: If the accession is missing or the project has no files.
    """
    accession = mdposit.extract_accession(repo_link)
    if not accession:
        raise BadRequest(description="Missing MDPosit project accession.")

    output_dir = DATA_DIR / experiment_id
    output_dir.mkdir(parents=True, exist_ok=True)

    try:
        mdposit.get_project(accession)
        with tempfile.TemporaryDirectory(dir=output_dir) as tmp_dir_name:
            tmp_dir = Path(tmp_dir_name)
            downloaded_paths = mdposit.download_project(accession, tmp_dir)
            resolved_tmp_dir = tmp_dir.resolve()

            for downloaded_path in downloaded_paths:
                source_path = Path(downloaded_path)
                relative_path = source_path.resolve().relative_to(resolved_tmp_dir)
                destination_path = output_dir / relative_path
                destination_path.parent.mkdir(parents=True, exist_ok=True)
                move(source_path, destination_path)
    except ValueError as exc:
        raise BadRequest(description=str(exc)) from exc
    except requests.HTTPError as exc:
        raise ApiError(
            HTTPStatus.INTERNAL_SERVER_ERROR,
            "Failed to download MDPosit project.",
            "urn:mddash:upstream-download-failed",
            "The MDPosit project couldn't be fetched; try again in a moment.",
        ) from exc
