"""Tuner API client (HTTP basic auth); `engine` is the API path segment (`gmx`, `amber`)."""

from pathlib import Path

import anyio
import httpx
from core.config import TUNER_PASSWORD, TUNER_URL, TUNER_USER

from clients.http import raise_for_status

POLL_TIMEOUT = 5
SUBMIT_TIMEOUT = 60
DELETE_TIMEOUT = 15


class TunerClient:
    """Tuning jobs and their trial logs."""

    def __init__(
        self,
        http: httpx.AsyncClient,
        base_url: str = TUNER_URL,
        auth: httpx.Auth | None = None,
    ) -> None:
        """Bind to the shared HTTP client."""
        self._http = http
        self._base_url = base_url
        self._auth = auth or httpx.BasicAuth(TUNER_USER, TUNER_PASSWORD)

    def _url(self, engine: str, path: str = "") -> str:
        return f"{self._base_url}/tuning-jobs/{engine}{path}"

    @staticmethod
    def _json(response: httpx.Response) -> dict:
        raise_for_status(response)
        if not response.text:
            return {}
        return response.json()

    async def submit(self, engine: str, files: dict[str, Path], nsteps: int, extra_args: str = "") -> dict:
        """Submit run inputs for tuning; `files` maps the form field to its file (`file` for GROMACS, `prmtop`/`inpcrd`/`mdin` for AMBER)."""
        uploads = {field: (path.name, await anyio.Path(path).read_bytes()) for field, path in files.items()}
        response = await self._http.post(
            self._url(engine),
            files=uploads,
            data={"nsteps": str(nsteps), "extra_args": extra_args},
            auth=self._auth,
            timeout=SUBMIT_TIMEOUT,
        )
        return self._json(response)

    async def poll_status(self, engine: str, job_id: str) -> dict:
        """
        Status of a tuning job with its trials.

        Raises:
            TimeoutError: If the tuner does not answer in time.
        """
        try:
            response = await self._http.get(
                self._url(engine, f"/{job_id}/status"), auth=self._auth, timeout=POLL_TIMEOUT
            )
        except httpx.TimeoutException as e:
            raise TimeoutError(f"Tuner poll status timed out for job {job_id}") from e
        return self._json(response)

    async def delete_job(self, engine: str, job_id: str) -> dict:
        """Delete a tuning job."""
        response = await self._http.delete(self._url(engine, f"/{job_id}"), auth=self._auth, timeout=DELETE_TIMEOUT)
        return self._json(response)

    async def trial_log(self, engine: str, job_id: str, trial_id: str, stream: str) -> str:
        """`stdout` or `stderr` of a tuning trial (empty until written)."""
        response = await self._http.get(
            self._url(engine, f"/{job_id}/trials/{trial_id}/{stream}"), auth=self._auth, timeout=POLL_TIMEOUT
        )
        raise_for_status(response)
        return response.text
