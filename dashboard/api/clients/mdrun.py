from http import HTTPStatus

import requests
from config import MDRUN_API_URL


def get_mdrun_response_data(response: requests.Response) -> dict:
    """
    Extract JSON data from an MDRun API response.

    Args:
        response: The response object from the MDRun API.

    Returns:
        The JSON data from the response.

    Raises:
        requests.HTTPError: If the request failed.
    """
    data = response.json()

    if not data["success"]:
        raise requests.HTTPError(data["message"], request=None, response=response)

    return data["data"]


# Legacy aliases (kept for backward compatibility)
def get_job(job_id: str) -> dict:
    """
    Get job status by job ID (legacy alias for get_gmx_job).

    Args:
        job_id: The ID of the job to retrieve.

    Returns:
        Job status data containing id and status.
    """
    return get_gmx_job(job_id)


def create_job(
    experiment_id: str, tpr_name: str, bucket_name: str, pme: str, nb: str, np: int, ntomp: int, extra_args: str = ""
) -> dict:
    """
    Create a new GROMACS MDRun job (legacy alias for create_gmx_job).

    Args:
        experiment_id: The experiment ID.
        tpr_name: Name of the TPR file.
        bucket_name: S3 bucket name.
        pme: PME device type ('auto', 'cpu', or 'gpu').
        nb: Non-bonded device type ('auto', 'cpu', or 'gpu').
        np: Number of MPI processes.
        ntomp: Number of OpenMP threads.
        extra_args: Additional arguments for the job.

    Returns:
        Created job data containing id and status.
    """
    return create_gmx_job(experiment_id, tpr_name, bucket_name, pme, nb, np, ntomp, extra_args)


def delete_job(job_id: str) -> None:
    """
    Delete a job by job ID (legacy alias for delete_gmx_job).

    Args:
        job_id: The ID of the job to delete.

    Raises:
        requests.HTTPError: If the request fails.
    """
    delete_gmx_job(job_id)


# GROMACS-specific functions
def get_gmx_job(job_id: str) -> dict:
    """
    Get GROMACS job status by job ID.

    Args:
        job_id: The ID of the job to retrieve.

    Returns:
        Job status data containing id and status.
    """
    response = requests.get(f"{MDRUN_API_URL}/jobs/gmx/{job_id}", timeout=5)
    return get_mdrun_response_data(response)


def create_gmx_job(
    experiment_id: str, tpr_name: str, bucket_name: str, pme: str, nb: str, np: int, ntomp: int, extra_args: str = ""
) -> dict:
    """
    Create a new GROMACS MDRun job.

    Args:
        experiment_id: The experiment ID.
        tpr_name: Name of the TPR file.
        bucket_name: S3 bucket name.
        pme: PME device type ('auto', 'cpu', or 'gpu').
        nb: Non-bonded device type ('auto', 'cpu', or 'gpu').
        np: Number of MPI processes.
        ntomp: Number of OpenMP threads.
        extra_args: Additional arguments for the job.

    Returns:
        Created job data containing id and status.
    """
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

    response = requests.post(f"{MDRUN_API_URL}/jobs/gmx", json=data, timeout=10)
    return get_mdrun_response_data(response)


def delete_gmx_job(job_id: str) -> None:
    """
    Delete a GROMACS job by job ID.

    Args:
        job_id: The ID of the job to delete.

    Raises:
        requests.HTTPError: If the request fails.
    """
    response = requests.delete(f"{MDRUN_API_URL}/jobs/gmx/{job_id}", timeout=10)

    # 404 = job already deleted or does not exist (success)
    if response.status_code == HTTPStatus.NOT_FOUND:
        return

    if not response.ok:
        raise requests.HTTPError(response.json()["message"], request=None, response=response)


# AMBER-specific functions
def get_amber_job(job_id: str) -> dict:
    """
    Get AMBER job status by job ID.

    Args:
        job_id: The ID of the job to retrieve.

    Returns:
        Job status data containing id and status.
    """
    response = requests.get(f"{MDRUN_API_URL}/jobs/amber/{job_id}", timeout=5)
    return get_mdrun_response_data(response)


def create_amber_job(
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
    """
    Create a new AMBER MDRun job.

    Args:
        experiment_id: The experiment ID.
        prmtop_name: Name of the PRMTOP topology file.
        inpcrd_name: Name of the INPCRD coordinate file.
        mdin_name: Name of the MDIN input file.
        bucket_name: S3 bucket name.
        binary: AMBER binary type ('pmemd.cuda' or 'pmemd.MPI').
        ewald: Ewald summation preset ('default' or 'optimized').
        np: Number of MPI processes.
        ntomp: Number of OpenMP threads.
        extra_args: Additional arguments for the job.

    Returns:
        Created job data containing id and status.
    """
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

    response = requests.post(f"{MDRUN_API_URL}/jobs/amber", json=data, timeout=10)
    return get_mdrun_response_data(response)


def delete_amber_job(job_id: str) -> None:
    """
    Delete an AMBER job by job ID.

    Args:
        job_id: The ID of the job to delete.

    Raises:
        requests.HTTPError: If the request fails.
    """
    response = requests.delete(f"{MDRUN_API_URL}/jobs/amber/{job_id}", timeout=10)

    # 404 = job already deleted or does not exist (success)
    if response.status_code == HTTPStatus.NOT_FOUND:
        return

    if not response.ok:
        raise requests.HTTPError(response.json()["message"], request=None, response=response)