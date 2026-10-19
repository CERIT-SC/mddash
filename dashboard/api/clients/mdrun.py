"""MDRun API client. The API returns raw resources on success and `{detail}` on error."""

from http import HTTPStatus

import httpx
from core.config import MDRUN_API_URL

from clients.http import raise_for_status

GET_TIMEOUT = 5
WRITE_TIMEOUT = 10


class MDRunClient:
    """GROMACS and AMBER jobs on the MDRun API; `engine` is the API path segment (`gmx`, `amber`)."""

    def __init__(self, http: httpx.AsyncClient, base_url: str = MDRUN_API_URL) -> None:
        """Bind to the shared HTTP client."""
        self._http = http
        self._base_url = base_url

    async def _json(self, method: str, path: str, request_timeout: float, json: dict | None = None) -> dict:
        response = await self._http.request(method, f"{self._base_url}{path}", timeout=request_timeout, json=json)
        raise_for_status(response)
        return response.json()

    @staticmethod
    def _ignore_missing(response: httpx.Response) -> None:
        # 404 = job already deleted or does not exist (success)
        if response.status_code == HTTPStatus.NOT_FOUND:
            return
        raise_for_status(response)

    async def get_job(self, engine: str, job_id: str) -> dict:
        """Job status (`id`, `status`)."""
        return await self._json("GET", f"/jobs/{engine}/{job_id}", GET_TIMEOUT)

    async def delete_job(self, engine: str, job_id: str) -> None:
        """Delete a job; a missing job counts as deleted."""
        self._ignore_missing(await self._http.delete(f"{self._base_url}/jobs/{engine}/{job_id}", timeout=WRITE_TIMEOUT))

    async def stop_job(self, engine: str, job_id: str) -> None:
        """Stop a job, preserving its data (checkpoint reaches S3 before teardown); a missing job counts as stopped."""
        self._ignore_missing(
            await self._http.post(f"{self._base_url}/jobs/{engine}/{job_id}/stop", timeout=WRITE_TIMEOUT)
        )

    async def create_gmx_job(
        self,
        experiment_id: str,
        tpr_name: str,
        bucket_name: str,
        pme: str,
        nb: str,
        np: int,
        ntomp: int,
        extra_args: str = "",
    ) -> dict:
        """Create a GROMACS job; returns the created job (`id`, `status`)."""
        data = {
            "experiment_id": experiment_id,
            "tpr_name": tpr_name,
            "bucket_name": bucket_name,
            "pme": pme,
            "nb": nb,
            "np": np,
            "ntomp": ntomp,
            "extra_args": extra_args,
        }
        return await self._json("POST", "/jobs/gmx", WRITE_TIMEOUT, json=data)

    async def create_amber_job(
        self,
        experiment_id: str,
        prmtop_name: str,
        inpcrd_name: str,
        mdin_name: str,
        bucket_name: str,
        binary: str,
        ewald: str,
        np: int,
        ntomp: int,
        extra_args: str = "",
    ) -> dict:
        """Create an AMBER job; returns the created job (`id`, `status`)."""
        data = {
            "experiment_id": experiment_id,
            "prmtop_name": prmtop_name,
            "inpcrd_name": inpcrd_name,
            "mdin_name": mdin_name,
            "bucket_name": bucket_name,
            "binary": binary,
            "ewald": ewald,
            "np": np,
            "ntomp": ntomp,
            "extra_args": extra_args,
        }
        return await self._json("POST", "/jobs/amber", WRITE_TIMEOUT, json=data)
