"""
MDRepo API client using OAuth2 Bearer token authentication.

This module provides functions to interact with the MDRepo (InvenioRDM) API
for creating experiments and uploading files.
"""

from pathlib import Path

import requests
from config import MDREPO_API_URL, MDREPO_RECORD_NAME


def _auth_header(token: str) -> dict[str, str]:
    """Create authorization header for API requests."""
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
