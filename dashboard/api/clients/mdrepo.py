"""
MDRepo API client using OAuth2 Bearer token authentication.

This module provides functions to interact with the MDRepo (InvenioRDM) API
for creating experiments and uploading files.
"""

import logging
import threading
from http import HTTPStatus
from pathlib import Path

import requests
from config import MDREPO_API_URL, MDREPO_RECORD_NAME
from utils import is_excluded_path

logger = logging.getLogger(__name__)


def _auth_header(token: str) -> dict[str, str]:
    """
    Create authorization header with Bearer token.

    Args:
        token: OAuth2 access token.

    Returns:
        Authorization header dictionary.
    """
    return {"Authorization": f"Bearer {token}"}


def create_experiment(access_token: str, community: str, metadata: dict) -> dict:
    """
    Create a new experiment (record) in MDRepo.

    Args:
        access_token: OAuth2 access token for authentication.
        community: Community slug to publish under.
        metadata: Metadata for the experiment.

    Returns:
        Server response containing the created experiment data.

    Raises:
        ValueError: If the experiment creation fails.
    """
    json_data = {
        "files": {"enabled": True},
        "parent": {"communities": {"default": community}},
        "metadata": metadata,
    }

    response = requests.post(
        f"{MDREPO_API_URL}/{MDREPO_RECORD_NAME}", json=json_data, headers=_auth_header(access_token), timeout=30
    )

    if not response.ok:
        raise ValueError(f"Failed to create experiment: {response.status_code} - {response.text}")

    return response.json()


def upload_file(access_token: str, experiment_id: str, file: Path, file_key: str) -> dict:
    """
    Upload a file to an experiment draft in MDRepo.

    Args:
        access_token: OAuth2 access token for authentication.
        experiment_id: Experiment (record) ID in MDRepo.
        file: Path to the file to upload.
        file_key: Key to use for the file (relative path).

    Returns:
        Server response from file commit.

    Raises:
        ValueError: If any step of the file upload fails.
    """
    headers = _auth_header(access_token)

    # Initialize file upload
    json_data = [{"key": file_key}]
    response = requests.post(
        f"{MDREPO_API_URL}/{MDREPO_RECORD_NAME}/{experiment_id}/draft/files",
        headers=headers,
        json=json_data,
        timeout=30,
    )

    if not response.ok:
        raise ValueError(f"Failed to initialize file upload: {response.status_code} - {response.text}")

    # Upload file content
    with file.open("rb") as f:
        response = requests.put(
            f"{MDREPO_API_URL}/{MDREPO_RECORD_NAME}/{experiment_id}/draft/files/{file_key}/content",
            headers=headers,
            data=f,
            stream=True,
            timeout=300,  # longer timeout for file uploads
        )

    if not response.ok:
        raise ValueError(f"Failed to upload file: {response.status_code} - {response.text}")

    # Commit the file
    response = requests.post(
        f"{MDREPO_API_URL}/{MDREPO_RECORD_NAME}/{experiment_id}/draft/files/{file_key}/commit",
        headers=headers,
        timeout=30,
    )

    if not response.ok:
        raise ValueError(f"Failed to commit file: {response.status_code} - {response.text}")

    return response.json()


def upload_experiment_files(
    access_token: str, experiment_id: str, experiment_dir: Path, base_dir: Path | None = None
) -> None:
    """
    Upload all experiment files that pass the upload filter.

    Recursively uploads files from subdirectories, using relative paths as file keys.

    Args:
        access_token: OAuth2 access token for authentication.
        experiment_id: Experiment (record) ID in MDRepo.
        experiment_dir: Local experiment directory.
        base_dir: Base directory for calculating relative paths (used internally for recursion).
    """
    if base_dir is None:
        base_dir = experiment_dir

    for item in experiment_dir.iterdir():
        if is_excluded_path(item, base_dir):
            continue

        if item.is_file():
            try:
                file_key = str(item.relative_to(base_dir))
                upload_file(access_token, experiment_id, item, file_key)
            except ValueError:
                logger.exception("Failed to upload file '%s' to MDRepo.", item.name)
        elif item.is_dir():
            upload_experiment_files(access_token, experiment_id, item, base_dir)


def check_experiment_status(access_token: str, experiment_id: str) -> bool | None:
    """
    Check if an experiment exists in MDRepo and whether it's published or draft.

    Args:
        access_token: OAuth2 access token for authentication.
        experiment_id: Experiment (record) ID in MDRepo.

    Returns:
        True if published, False if draft, None if deleted (404).

    Raises:
        requests.RequestException: If there's a network error or non-404 HTTP error.
    """
    # Check if published
    response = requests.get(
        f"{MDREPO_API_URL}/{MDREPO_RECORD_NAME}/{experiment_id}",
        headers=_auth_header(access_token),
        timeout=30,
    )
    if response.status_code == HTTPStatus.OK:
        return True
    if response.status_code != HTTPStatus.NOT_FOUND:
        response.raise_for_status()

    # Check if draft
    response = requests.get(
        f"{MDREPO_API_URL}/{MDREPO_RECORD_NAME}/{experiment_id}/draft",
        headers=_auth_header(access_token),
        timeout=30,
    )
    if response.status_code == HTTPStatus.OK:
        return False
    if response.status_code != HTTPStatus.NOT_FOUND:
        response.raise_for_status()

    return None


def start_upload_worker(access_token: str, experiment_id: str, experiment_dir: Path) -> threading.Thread:
    """
    Start a background thread to upload experiment files to MDRepo.

    Args:
        access_token: OAuth2 access token for authentication.
        experiment_id: Experiment (record) ID in MDRepo.
        experiment_dir: Local experiment directory.

    Returns:
        The started daemon thread.
    """

    def _worker() -> None:
        try:
            upload_experiment_files(access_token, experiment_id, experiment_dir)
        except Exception:
            logger.exception("Unexpected error in MDRepo upload worker")

    thread = threading.Thread(target=_worker, daemon=True)
    thread.start()
    return thread
