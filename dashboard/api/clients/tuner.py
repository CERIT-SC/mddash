from pathlib import Path

import requests
from config import TUNER_PASSWORD, TUNER_URL, TUNER_USER
from requests import HTTPError, Response
from requests.auth import HTTPBasicAuth
from requests.exceptions import Timeout

AUTH = HTTPBasicAuth(TUNER_USER, TUNER_PASSWORD)

POLL_TIMEOUT = 5
SUBMIT_TIMEOUT = 60
DELETE_TIMEOUT = 15


def _extract_response_data(response: Response) -> dict:
    response.raise_for_status()
    data = response.json()

    if not data["success"]:
        raise HTTPError(data["message"], request=None, response=response)

    return data["data"]


def gmx_submit(tpr_path: Path, nsteps: int = 25_000, extra_args: str = "") -> dict:
    """
    Submit a GROMACS TPR file for parameter tuning.

    Args:
        tpr_path: The .tpr file for the simulation to be tuned.
        nsteps: Number of steps to run in GROMACS mdrun (default: 25_000).
        extra_args: Additional GROMACS mdrun arguments (default: "").

    Returns:
        The response from the tuner.
    """
    with tpr_path.open("rb") as f:
        files = {"file": f}
        data = {"nsteps": nsteps, "extra_args": extra_args}
        response = requests.post(
            f"{TUNER_URL}/gmx/tuning-jobs", files=files, data=data, auth=AUTH, timeout=SUBMIT_TIMEOUT
        )
    return _extract_response_data(response)


def gmx_poll_status(job_id: str) -> dict:
    """
    Poll the status of a submitted GROMACS tuning job.

    Args:
        job_id: The ID of the job to poll.

    Returns:
        The response from the tuner.

    Raises:
        TimeoutError: If the request timed out.
    """
    try:
        response = requests.get(f"{TUNER_URL}/gmx/tuning-jobs/{job_id}/status", auth=AUTH, timeout=POLL_TIMEOUT)
        return _extract_response_data(response)
    except Timeout as e:
        raise TimeoutError(f"Tuner poll status timed out for job {job_id}") from e


def gmx_delete_job(job_id: str) -> dict:
    """
    Delete a submitted GROMACS tuning job.

    Args:
        job_id: The ID of the job to delete.

    Returns:
        The response from the tuner.
    """
    response = requests.delete(f"{TUNER_URL}/gmx/tuning-jobs/{job_id}", auth=AUTH, timeout=DELETE_TIMEOUT)
    return _extract_response_data(response)


def amber_submit(
    prmtop_path: Path, inpcrd_path: Path, mdin_path: Path, nsteps: int = 25_000, extra_args: str = ""
) -> dict:
    """
    Submit an AMBER simulation for parameter tuning.

    Args:
        prmtop_path: AMBER parameter/topology file (.prmtop or .parm7).
        inpcrd_path: AMBER coordinate/restart file (.inpcrd, .rst7, or .nc).
        mdin_path: AMBER input file (.mdin).
        nsteps: Number of steps to run in pmemd (default: 25_000).
        extra_args: Additional pmemd arguments (default: "").

    Returns:
        The response from the tuner.
    """
    with prmtop_path.open("rb") as prmtop, inpcrd_path.open("rb") as inpcrd, mdin_path.open("rb") as mdin:
        files = {"prmtop": prmtop, "inpcrd": inpcrd, "mdin": mdin}
        data = {"nsteps": nsteps, "extra_args": extra_args}
        response = requests.post(
            f"{TUNER_URL}/amber/tuning-jobs", files=files, data=data, auth=AUTH, timeout=SUBMIT_TIMEOUT
        )
    return _extract_response_data(response)


def amber_poll_status(job_id: str) -> dict:
    """
    Poll the status of a submitted AMBER tuning job.

    Args:
        job_id: The ID of the job to poll.

    Returns:
        The response from the tuner.

    Raises:
        TimeoutError: If the request timed out.
    """
    try:
        response = requests.get(f"{TUNER_URL}/amber/tuning-jobs/{job_id}/status", auth=AUTH, timeout=POLL_TIMEOUT)
        return _extract_response_data(response)
    except Timeout as e:
        raise TimeoutError(f"Tuner poll status timed out for job {job_id}") from e


def amber_delete_job(job_id: str) -> dict:
    """
    Delete a submitted AMBER tuning job.

    Args:
        job_id: The ID of the job to delete.

    Returns:
        The response from the tuner.
    """
    response = requests.delete(f"{TUNER_URL}/amber/tuning-jobs/{job_id}", auth=AUTH, timeout=DELETE_TIMEOUT)
    return _extract_response_data(response)


# DEMO
if __name__ == "__main__":
    tpr_path = Path(__file__).parent.parent / "_demo" / "data" / "md.tpr"

    # Submit a job
    response = gmx_submit(tpr_path, nsteps=25000, extra_args="")
    print("Submitted job:", response)

    print("Waiting for job to start...")
    from time import sleep

    sleep(2)

    # Poll the status
    run_id = response["id"]
    status = gmx_poll_status(run_id)
    print("Job status:", status)

    # Delete the job
    delete_response = gmx_delete_job(run_id)
    print("Deleted job:", delete_response)
