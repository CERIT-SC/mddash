import requests
from config import MDRUN_API_URL


def get_mdrun_response_data(response: requests.Response) -> dict:
    """
    Extract JSON data from an MDRun API response.

    :param response: The response object from the MDRun API.
    :return: The JSON data from the response.
    :raise requests.HTTPError: If the request failed.
    :raise ValueError: If the response does not contain valid JSON.
    """
    data = response.json()

    if data['success'] != True:
        raise requests.HTTPError(data['message'], request=None, response=response)

    return data['data']


def get_job(job_id: str) -> dict:
    """
    Get job status by job ID.

    :param job_id: The ID of the job to retrieve
    :return: Job status data containing id and status
    :raise requests.HTTPError: If the request fails
    """
    response = requests.get(f'{MDRUN_API_URL}/jobs/{job_id}')
    return get_mdrun_response_data(response)


def create_job(
    experiment_id: str,
    tpr_name: str,
    bucket_name: str,
    pme: str,
    nb: str,
    np: int,
    ntomp: int,
    extra_args: str = ''
) -> dict:
    """
    Create a new MDRun job.

    :param experiment_id: The experiment ID
    :param tpr_name: Name of the TPR file
    :param bucket_name: S3 bucket name
    :param pme: PME device type ('auto', 'cpu', or 'gpu')
    :param nb: Non-bonded device type ('auto', 'cpu', or 'gpu')
    :param np: Number of MPI processes
    :param ntomp: Number of OpenMP threads
    :param extra_args: Additional arguments for the job (optional)
    :return: Created job data containing id and status
    :raise requests.HTTPError: If the request fails
    """
    data = {
        'experiment_id': experiment_id,
        'tpr_name': tpr_name,
        'bucket_name': bucket_name,
        'pme': pme,
        'nb': nb,
        'np': np,
        'ntomp': ntomp,
        'extra_args': extra_args
    }

    response = requests.post(f'{MDRUN_API_URL}/jobs', json=data)
    return get_mdrun_response_data(response)


def delete_job(job_id: str) -> None:
    """
    Delete a job by job ID.

    :param job_id: The ID of the job to delete
    :return: Success message
    :raise requests.HTTPError: If the request fails
    """
    response = requests.delete(f'{MDRUN_API_URL}/jobs/{job_id}')

    # 404 = job already deleted or does not exist (success)
    if response.status_code == 404:
        return None

    if not response.ok:
        raise requests.HTTPError(response.json()['message'], request=None, response=response)
