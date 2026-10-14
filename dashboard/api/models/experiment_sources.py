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

import anyio
import httpx
from clients import mdposit
from clients.http import client
from config import DATA_DIR
from errors import ApiError, BadRequest, InternalServerError, NotFound
from validators import validate_fetch_target, validate_http_url

if TYPE_CHECKING:
    from .experiment import Experiment
    from .simulation import Simulation

logger = logging.getLogger(__name__)

_REDIRECT_STATUSES = {301, 302, 303, 307, 308}
_PDB_STRUCTURE_RECORDS = {"ATOM", "HETATM"}
_DOWNLOAD_CHUNK_BYTES = 128 * 1024


def list_simulations(experiment: Experiment) -> list[Simulation]:
    """List the simulations of an experiment (deferred import: Simulation imports the Experiment model)."""
    from .simulation import Simulation  # ruff:ignore[import-outside-top-level]

    return Simulation.list(experiment.id, experiment)


async def fetch_pdb(url: str, *, max_redirects: int = 5) -> httpx.Response:
    """
    Fetch a PDB URL, following redirects manually so every hop is SSRF-validated.

    Returns:
        The final non-redirect response.

    Raises:
        InternalServerError: If the redirect chain exceeds max_redirects.
    """
    for _ in range(max_redirects + 1):
        await anyio.to_thread.run_sync(validate_fetch_target, url)
        response = await client().get(url, timeout=30, follow_redirects=False)
        if response.status_code not in _REDIRECT_STATUSES:
            return response
        location = response.headers.get("Location")
        if not location:
            return response
        url = validate_http_url(urljoin(url, location))
    raise InternalServerError("Too many redirects while downloading PDB file.")


def validate_pdb_content(content: bytes) -> None:
    """
    Reject downloaded content that is not a valid PDB structure file.

    Catches HTML error pages, login redirects, and binary responses that return
    200 but are not valid PDB files. A structural file must contain at least one
    ATOM or HETATM record (columns 1-6).

    Raises:
        BadRequest: If no ATOM/HETATM record is present.
    """
    text = content.decode("utf-8", errors="replace")
    for line in text.splitlines():
        if line[:6].strip() in _PDB_STRUCTURE_RECORDS:
            return
    raise BadRequest("Downloaded content is not a valid PDB file (no ATOM or HETATM records).")


async def resolve_repo_link(repo_link: str) -> str:
    """Follow DOI redirects to reach the final repository URL."""
    resolved = repo_link.strip().rstrip("/")
    if urlparse(resolved).netloc == "doi.org":
        response = await client().head(resolved, follow_redirects=True, timeout=30)
        resolved = str(response.url).rstrip("/")
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
            raise BadRequest(f"Unsafe path in repository archive: {member.filename}") from exc
        zf.extract(member, output_dir)


def _extract_zip_file(zip_path: Path, output_dir: Path) -> None:
    with zipfile.ZipFile(zip_path) as zf:
        safe_extract_zip(zf, output_dir)


async def import_invenio_repo(repo_link: str, experiment_id: str) -> None:
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
        async with client().stream("GET", url, timeout=300) as response:
            if response.status_code == HTTPStatus.NOT_FOUND:
                raise NotFound(f"Repository '{repo_link}' not found.")
            if response.status_code != HTTPStatus.OK:
                raise ApiError(
                    HTTPStatus.INTERNAL_SERVER_ERROR,
                    "Failed to download repository.",
                    "urn:mddash:upstream-download-failed",
                    "The repository couldn't be fetched; check the URL or try again in a moment.",
                )
            async with await anyio.open_file(tmp_path, "wb") as out:
                async for chunk in response.aiter_bytes(_DOWNLOAD_CHUNK_BYTES):
                    await out.write(chunk)

        await anyio.to_thread.run_sync(_extract_zip_file, tmp_path, DATA_DIR / experiment_id)


def _move_downloads(downloaded_paths: list[Path], tmp_dir: Path, output_dir: Path) -> None:
    resolved_tmp_dir = tmp_dir.resolve()
    for downloaded_path in downloaded_paths:
        relative_path = downloaded_path.resolve().relative_to(resolved_tmp_dir)
        destination_path = output_dir / relative_path
        destination_path.parent.mkdir(parents=True, exist_ok=True)
        move(downloaded_path, destination_path)


async def import_mdposit_repo(repo_link: str, experiment_id: str) -> None:
    """
    Download an MDPosit project into the experiment directory.

    Raises:
        BadRequest: If the accession is missing or the project has no files.
    """
    accession = mdposit.extract_accession(repo_link)
    if not accession:
        raise BadRequest("Missing MDPosit project accession.")

    output_dir = DATA_DIR / experiment_id
    await anyio.Path(output_dir).mkdir(parents=True, exist_ok=True)

    try:
        await mdposit.get_project(accession)
        with tempfile.TemporaryDirectory(dir=output_dir) as tmp_dir_name:
            tmp_dir = Path(tmp_dir_name)
            downloaded_paths = await mdposit.download_project(accession, tmp_dir)
            await anyio.to_thread.run_sync(_move_downloads, downloaded_paths, tmp_dir, output_dir)
    except ValueError as exc:
        raise BadRequest(str(exc)) from exc
    except httpx.HTTPStatusError as exc:
        raise ApiError(
            HTTPStatus.INTERNAL_SERVER_ERROR,
            "Failed to download MDPosit project.",
            "urn:mddash:upstream-download-failed",
            "The MDPosit project couldn't be fetched; try again in a moment.",
        ) from exc
