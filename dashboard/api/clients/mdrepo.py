"""
MDRepo (InvenioRDM) API client using OAuth2 Bearer token authentication.

File uploads run in a dedicated Kubernetes Job (see ``modules/publishing/submission.py``
and the ``mdrepo-uploader`` worker image), not in this process.
"""

import logging
from http import HTTPStatus

import httpx
from core.config import MDREPO_API_URL, MDREPO_RECORD_NAME, MDREPO_TOKEN_URL, MDREPO_URL

logger = logging.getLogger(__name__)


def _auth_header(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


class MDRepoClient:
    """MDRepo records and the OAuth token endpoint."""

    def __init__(
        self,
        http: httpx.AsyncClient,
        url: str = MDREPO_URL,
        api_url: str = MDREPO_API_URL,
        record_name: str = MDREPO_RECORD_NAME,
        token_url: str = MDREPO_TOKEN_URL,
    ) -> None:
        """Bind to the shared HTTP client."""
        self._http = http
        self._url = url
        self._api_url = api_url
        self._record_name = record_name
        self._token_url = token_url

    async def request_token(self, data: dict[str, str]) -> httpx.Response:
        """POST an OAuth grant (authorization code or refresh token) to the token endpoint."""
        return await self._http.post(self._token_url, data=data, timeout=30)

    async def create_experiment(self, access_token: str, community: str, metadata: dict) -> dict:
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
        response = await self._http.post(
            f"{self._api_url}/{self._record_name}", json=json_data, headers=_auth_header(access_token), timeout=30
        )
        if not response.is_success:
            raise ValueError(f"Failed to create experiment: {response.status_code} - {response.text}")
        return response.json()

    async def check_experiment_status(self, access_token: str, experiment_id: str) -> bool | None:
        """
        Check whether an MDRepo record is published or a draft.

        Returns:
            True if published, False if draft, None if deleted (404).
        """
        base = f"{self._api_url}/{self._record_name}/{experiment_id}"
        for url, published in ((base, True), (f"{base}/draft", False)):
            response = await self._http.get(url, headers=_auth_header(access_token), timeout=30)
            if response.status_code == HTTPStatus.OK:
                return published
            if response.status_code != HTTPStatus.NOT_FOUND:
                response.raise_for_status()
        return None

    async def is_token_valid(self, access_token: str) -> bool:
        """Whether MDRepo accepts the token (`/api/me`)."""
        response = await self._http.get(f"{self._url}/api/me", headers=_auth_header(access_token), timeout=10)
        return response.status_code == HTTPStatus.OK
