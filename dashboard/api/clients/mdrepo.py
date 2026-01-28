"""
MDRepo API client using OAuth2 Bearer token authentication.

This module provides functions to interact with the MDRepo (InvenioRDM) API
for creating experiments and uploading files.
"""

import logging
import threading
from pathlib import Path

import requests
from config import MDREPO_API_URL, MDREPO_RECORD_NAME
from utils import is_excluded_path

logger = logging.getLogger(__name__)


def _auth_header(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def create_experiment(token: str, community: str, metadata: dict) -> dict:
    """
    Create a new experiment (record) in MDRepo.

    Args:
        token: OAuth2 access token.
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
        f"{MDREPO_API_URL}/{MDREPO_RECORD_NAME}", json=json_data, headers=_auth_header(token), timeout=30
    )

    if not response.ok:
        raise ValueError(f"Failed to create experiment: {response.status_code} - {response.text}")

    return response.json()


def upload_file(token: str, experiment_id: str, file: Path) -> dict:
    """
    Upload a file to an experiment draft in MDRepo.

    Args:
        token: OAuth2 access token.
        experiment_id: Experiment (record) ID in MDRepo.
        file: Path to the file to upload.

    Returns:
        Server response from file commit.

    Raises:
        ValueError: If any step of the file upload fails.
    """
    headers = _auth_header(token)

    # Initialize file upload
    json_data = [{"key": file.name}]
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
            f"{MDREPO_API_URL}/{MDREPO_RECORD_NAME}/{experiment_id}/draft/files/{file.name}/content",
            headers=headers,
            data=f,
            stream=True,
            timeout=300,  # longer timeout for file uploads
        )

    if not response.ok:
        raise ValueError(f"Failed to upload file: {response.status_code} - {response.text}")

    # Commit the file
    response = requests.post(
        f"{MDREPO_API_URL}/{MDREPO_RECORD_NAME}/{experiment_id}/draft/files/{file.name}/commit",
        headers=headers,
        timeout=30,
    )

    if not response.ok:
        raise ValueError(f"Failed to commit file: {response.status_code} - {response.text}")

    return response.json()


def upload_experiment_files(token: str, experiment_id: str, experiment_dir: Path) -> None:
    """
    Upload all experiment files that pass the upload filter.

    Args:
        token: OAuth2 access token.
        experiment_id: Experiment (record) ID in MDRepo.
        experiment_dir: Local experiment directory.
    """
    for file in experiment_dir.iterdir():
        # TODO: Should we upload subdirectories?
        if not file.is_file():
            continue
        if is_excluded_path(file, experiment_dir):
            continue

        try:
            upload_file(token, experiment_id, file)
        except ValueError:
            logger.exception("Failed to upload file '%s' to MDRepo.", file.name)


def start_upload_worker(token: str, experiment_id: str, experiment_dir: Path) -> threading.Thread:
    """
    Start a background thread to upload experiment files to MDRepo.

    Args:
        token: OAuth2 access token.
        experiment_id: Experiment (record) ID in MDRepo.
        experiment_dir: Local experiment directory.

    Returns:
        The started daemon thread.
    """

    def _worker() -> None:
        try:
            upload_experiment_files(token, experiment_id, experiment_dir)
        except Exception:
            logger.exception("Unexpected error in MDRepo upload worker")

    thread = threading.Thread(target=_worker, daemon=True)
    thread.start()
    return thread
