from pathlib import Path

import requests
from config import TUNER_PASSWORD, TUNER_URL, TUNER_USER
from requests import HTTPError, Response
from requests.auth import HTTPBasicAuth

AUTH = HTTPBasicAuth(TUNER_USER, TUNER_PASSWORD)


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

    if data["success"] != True:
        raise HTTPError(data["message"], request=None, response=response)

    return data["data"]


def run_submit(tpr_path: Path) -> dict:
    """
    Submit a TPR to get tuned.

    Args:
        tpr_path: The .tpr file for the simulation to be tuned.

    Returns:
        The response from the tuner.

    Raises:
        FileNotFoundError: If the TPR file does not exist.
        HTTPError: If the request fails.
    """
    with tpr_path.open("rb") as f:
        files = {"file": f}
        response = requests.post(f"{TUNER_URL}/tuner_runs", files=files, auth=AUTH, timeout=30)
    return get_tuner_response_data(response)


def poll_status(job_id: str) -> dict:
    """
    Poll the status of a submitted job.

    Args:
        job_id: The ID of the job to poll.

    Returns:
        The response from the tuner.

    Raises:
        HTTPError: If the request fails.
    """
    response = requests.get(f"{TUNER_URL}/tuner_runs/{job_id}/status", auth=AUTH, timeout=5)
    return get_tuner_response_data(response)


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
    response = requests.delete(f"{TUNER_URL}/tuner_runs/{job_id}", auth=AUTH, timeout=10)
    return get_tuner_response_data(response)


# DEMO
if __name__ == "__main__":
    tpr_path = Path(__file__).parent.parent / "_demo" / "md.tpr"

    # Submit a job
    response = run_submit(tpr_path)
    print("Submitted job:", response)

    print("Waiting for job to start...")
    from time import sleep

    sleep(2)

    # Poll the status
    run_id = response["tuner_run_id"]
    status = poll_status(run_id)
    print("Job status:", status)

    # Delete the job
    delete_response = delete_job(run_id)
    print("Deleted job:", delete_response)
