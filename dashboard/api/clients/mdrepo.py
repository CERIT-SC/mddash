"""
MDRepo (InvenioRDM) API client using OAuth2 Bearer token authentication.

File uploads run in a dedicated Kubernetes Job (see ``upload/submission.py``
and the ``mdrepo-uploader`` worker image), not in this process.
"""

import logging
from http import HTTPStatus

from core.config import MDREPO_API_URL, MDREPO_RECORD_NAME, MDREPO_URL

from clients.http import client

logger = logging.getLogger(__name__)


def _auth_header(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


async def create_experiment(access_token: str, community: str, metadata: dict) -> dict:
    """
    Create a new experiment (record draft) in MDRepo.

    Raises:
        ValueError: If the experiment creation fails.
    """
    json_data = {
        "files": {"enabled": True},
        "parent": {"communities": {"default": community}},
        "metadata": metadata,
    }
    response = await client().post(
        f"{MDREPO_API_URL}/{MDREPO_RECORD_NAME}", json=json_data, headers=_auth_header(access_token), timeout=30
    )
    if not response.is_success:
        raise ValueError(f"Failed to create experiment: {response.status_code} - {response.text}")
    return response.json()


async def check_experiment_status(access_token: str, experiment_id: str) -> bool | None:
    """
    Check whether an MDRepo record is published or a draft.

    Returns:
        True if published, False if draft, None if deleted (404).
    """
    base = f"{MDREPO_API_URL}/{MDREPO_RECORD_NAME}/{experiment_id}"
    for url, published in ((base, True), (f"{base}/draft", False)):
        response = await client().get(url, headers=_auth_header(access_token), timeout=30)
        if response.status_code == HTTPStatus.OK:
            return published
        if response.status_code != HTTPStatus.NOT_FOUND:
            response.raise_for_status()
    return None


async def is_token_valid(access_token: str) -> bool:
    """Whether MDRepo accepts the token (`/api/me`)."""
    response = await client().get(f"{MDREPO_URL}/api/me", headers=_auth_header(access_token), timeout=10)
    return response.status_code == HTTPStatus.OK
