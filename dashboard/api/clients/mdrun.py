"""MDRun API client. The API returns raw resources on success and `{detail}` on error."""

from http import HTTPStatus

from core.config import MDRUN_API_URL

from clients.http import client, raise_for_status

GET_TIMEOUT = 5
WRITE_TIMEOUT = 10


async def _json(method: str, url: str, request_timeout: float, json: dict | None = None) -> dict:
    response = await client().request(method, url, timeout=request_timeout, json=json)
    raise_for_status(response)
    return response.json()


async def _delete(url: str) -> None:
    response = await client().delete(url, timeout=WRITE_TIMEOUT)
    # 404 = job already deleted or does not exist (success)
    if response.status_code == HTTPStatus.NOT_FOUND:
        return
    raise_for_status(response)


async def get_gmx_job(job_id: str) -> dict:
    """GROMACS job status (`id`, `status`)."""
    return await _json("GET", f"{MDRUN_API_URL}/jobs/gmx/{job_id}", GET_TIMEOUT)


async def create_gmx_job(
    experiment_id: str, tpr_name: str, bucket_name: str, pme: str, nb: str, np: int, ntomp: int, extra_args: str = ""
) -> dict:
    """Create a GROMACS MDRun job; returns the created job (`id`, `status`)."""
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
    return await _json("POST", f"{MDRUN_API_URL}/jobs/gmx", WRITE_TIMEOUT, json=data)


async def delete_gmx_job(job_id: str) -> None:
    """Delete a GROMACS job; a missing job counts as deleted."""
    await _delete(f"{MDRUN_API_URL}/jobs/gmx/{job_id}")


async def stop_job(job_id: str, engine: str) -> None:
    """Stop a job, preserving its data (checkpoint reaches S3 before teardown)."""
    response = await client().post(f"{MDRUN_API_URL}/jobs/{engine}/{job_id}/stop", timeout=WRITE_TIMEOUT)
    # 404 = job already gone (success), same convention as the delete calls
    if response.status_code == HTTPStatus.NOT_FOUND:
        return
    raise_for_status(response)


async def get_amber_job(job_id: str) -> dict:
    """AMBER job status (`id`, `status`)."""
    return await _json("GET", f"{MDRUN_API_URL}/jobs/amber/{job_id}", GET_TIMEOUT)


async def create_amber_job(
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
    """Create an AMBER MDRun job; returns the created job (`id`, `status`)."""
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
    return await _json("POST", f"{MDRUN_API_URL}/jobs/amber", WRITE_TIMEOUT, json=data)


async def delete_amber_job(job_id: str) -> None:
    """Delete an AMBER job; a missing job counts as deleted."""
    await _delete(f"{MDRUN_API_URL}/jobs/amber/{job_id}")
