"""Tuner API client (HTTP basic auth)."""

from pathlib import Path

import anyio
import httpx
from core.config import TUNER_PASSWORD, TUNER_URL, TUNER_USER

from clients.http import client, raise_for_status

AUTH = httpx.BasicAuth(TUNER_USER, TUNER_PASSWORD)

POLL_TIMEOUT = 5
SUBMIT_TIMEOUT = 60
DELETE_TIMEOUT = 15


def _handle_response(response: httpx.Response) -> dict:
    raise_for_status(response)
    if not response.text:
        return {}
    return response.json()


async def _submit(engine: str, files: dict[str, Path], nsteps: int, extra_args: str) -> dict:
    uploads = {field: (path.name, await anyio.Path(path).read_bytes()) for field, path in files.items()}
    response = await client().post(
        f"{TUNER_URL}/tuning-jobs/{engine}",
        files=uploads,
        data={"nsteps": str(nsteps), "extra_args": extra_args},
        auth=AUTH,
        timeout=SUBMIT_TIMEOUT,
    )
    return _handle_response(response)


async def _poll_status(engine: str, job_id: str) -> dict:
    try:
        response = await client().get(
            f"{TUNER_URL}/tuning-jobs/{engine}/{job_id}/status", auth=AUTH, timeout=POLL_TIMEOUT
        )
    except httpx.TimeoutException as e:
        raise TimeoutError(f"Tuner poll status timed out for job {job_id}") from e
    return _handle_response(response)


async def _delete_job(engine: str, job_id: str) -> dict:
    response = await client().delete(f"{TUNER_URL}/tuning-jobs/{engine}/{job_id}", auth=AUTH, timeout=DELETE_TIMEOUT)
    return _handle_response(response)


async def _trial_log(engine: str, job_id: str, trial_id: str, stream: str) -> str:
    response = await client().get(
        f"{TUNER_URL}/tuning-jobs/{engine}/{job_id}/trials/{trial_id}/{stream}", auth=AUTH, timeout=POLL_TIMEOUT
    )
    raise_for_status(response)
    return response.text


async def gmx_submit(tpr_path: Path, nsteps: int, extra_args: str = "") -> dict:
    """Submit a GROMACS TPR file for parameter tuning."""
    return await _submit("gmx", {"file": tpr_path}, nsteps, extra_args)


async def gmx_poll_status(job_id: str) -> dict:
    """Poll the status of a GROMACS tuning job (TimeoutError when the tuner does not answer in time)."""
    return await _poll_status("gmx", job_id)


async def gmx_delete_job(job_id: str) -> dict:
    """Delete a GROMACS tuning job."""
    return await _delete_job("gmx", job_id)


async def amber_submit(
    prmtop_path: Path, inpcrd_path: Path, mdin_path: Path, nsteps: int, extra_args: str = ""
) -> dict:
    """Submit an AMBER simulation (prmtop, inpcrd, mdin) for parameter tuning."""
    files = {"prmtop": prmtop_path, "inpcrd": inpcrd_path, "mdin": mdin_path}
    return await _submit("amber", files, nsteps, extra_args)


async def amber_poll_status(job_id: str) -> dict:
    """Poll the status of an AMBER tuning job (TimeoutError when the tuner does not answer in time)."""
    return await _poll_status("amber", job_id)


async def amber_delete_job(job_id: str) -> dict:
    """Delete an AMBER tuning job."""
    return await _delete_job("amber", job_id)


async def gmx_get_trial_stdout(job_id: str, trial_id: str) -> str:
    """Stdout of a GROMACS tuning trial (empty until written)."""
    return await _trial_log("gmx", job_id, trial_id, "stdout")


async def gmx_get_trial_stderr(job_id: str, trial_id: str) -> str:
    """Stderr of a GROMACS tuning trial (empty until written)."""
    return await _trial_log("gmx", job_id, trial_id, "stderr")


async def amber_get_trial_stdout(job_id: str, trial_id: str) -> str:
    """Stdout of an AMBER tuning trial (empty until written)."""
    return await _trial_log("amber", job_id, trial_id, "stdout")


async def amber_get_trial_stderr(job_id: str, trial_id: str) -> str:
    """Stderr of an AMBER tuning trial (empty until written)."""
    return await _trial_log("amber", job_id, trial_id, "stderr")
