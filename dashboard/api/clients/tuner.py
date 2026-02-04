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


def get_tuner_response_data(response: Response) -> dict:
    """
    Extract JSON data from a tuner response.

    Args:
        response: The response object from the tuner API.

    Returns:
        The JSON data from the response.

    Raises:
        HTTPError: If the request failed.
        ValueError: If the response does not contain valid JSON.
    """
    response.raise_for_status()
    data = response.json()

    if not data["success"]:
        raise HTTPError(data["message"], request=None, response=response)

    return data["data"]


def run_submit(tpr_path: Path, nsteps: int = 25000, extra_args: str = "") -> dict:
    """
    Submit a TPR to get tuned.

    Args:
        tpr_path: The .tpr file for the simulation to be tuned.
        nsteps: Number of steps to run in GROMACS mdrun (default: 25000).
        extra_args: Additional GROMACS mdrun arguments (default: "").

    Returns:
        The response from the tuner.

    Raises:
        FileNotFoundError: If the TPR file does not exist.
        HTTPError: If the request fails.
    """
    with tpr_path.open("rb") as f:
        files = {"file": f}
        data = {"nsteps": nsteps, "extra_args": extra_args}
        response = requests.post(f"{TUNER_URL}/tuner_runs", files=files, data=data, auth=AUTH, timeout=SUBMIT_TIMEOUT)
    return get_tuner_response_data(response)


def poll_status(job_id: str) -> dict:
    """
    Poll the status of a submitted job.

    Args:
        job_id: The ID of the job to poll.

    Returns:
        The response from the tuner.

    Raises:
        TimeoutError: If the request timed out.
        HTTPError: If the request fails.
    """
    try:
        response = requests.get(f"{TUNER_URL}/tuner_runs/{job_id}/status", auth=AUTH, timeout=POLL_TIMEOUT)
        return get_tuner_response_data(response)
    except Timeout as e:
        raise TimeoutError(f"Tuner poll status timed out for job {job_id}") from e


def delete_job(job_id: str) -> dict:
    """
    Delete a submitted job.

    Args:
        job_id: The ID of the job to delete.

    Returns:
        The response from the tuner.

    Raises:
        HTTPError: If the request fails.
    """
    response = requests.delete(f"{TUNER_URL}/tuner_runs/{job_id}", auth=AUTH, timeout=DELETE_TIMEOUT)
    return get_tuner_response_data(response)


# DEMO
if __name__ == "__main__":
    tpr_path = Path(__file__).parent.parent / "_demo" / "data" / "md.tpr"

    # Submit a job
    response = run_submit(tpr_path, nsteps=25000, extra_args="")
    print("Submitted job:", response)

    print("Waiting for job to start...")
    from time import sleep

    sleep(2)

    # Poll the status
    run_id = response["id"]
    status = poll_status(run_id)
    print("Job status:", status)

    # Delete the job
    delete_response = delete_job(run_id)
    print("Deleted job:", delete_response)
