"""
MDRepo API client using OAuth2 Bearer token authentication.

This module provides functions to interact with the MDRepo (InvenioRDM) API
for creating experiment drafts and checking their publication status.

File uploads are performed by a dedicated Kubernetes Job (see
``upload/submission.py`` and the ``mdrepo-uploader`` worker image), not by
a daemon thread in this process.
"""

import logging
from http import HTTPStatus

import requests
from config import MDREPO_API_URL, MDREPO_RECORD_NAME

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


def check_experiment_status(access_token: str, experiment_id: str) -> bool | None:
    """
    Check if an experiment exists in MDRepo and whether it's published or draft.

    Args:
        access_token: OAuth2 access token for authentication.
        experiment_id: Experiment (record) ID in MDRepo.

    Returns:
        True if published, False if draft, None if deleted (404).
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
