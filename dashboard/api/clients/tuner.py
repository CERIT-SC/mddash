import requests
from requests import Response, HTTPError
from requests.auth import HTTPBasicAuth
from pathlib import Path


# TUNER_URL = 'https://gromacs-tuner.dyn.cloud.e-infra.cz/api'
TUNER_URL = 'http://gromacs-tuner-api-svc.gromacs-tuner-ns.svc.cluster.local:8000/api'
TUNER_USERNAME = 'admin'
TUNER_PASSWORD = 'strong-secret-here'
AUTH = HTTPBasicAuth(TUNER_USERNAME, TUNER_PASSWORD)


def get_tuner_response_data(response: Response) -> dict:
    '''
    Extract JSON data from a tuner response.

    :param response: The response object from the tuner API.
    :return: The JSON data from the response.
    :raise HTTPError: If the request failed.
    :raise ValueError: If the response does not contain valid JSON.
    '''
    response.raise_for_status()
    data = response.json()

    if data['success'] != True:
        raise HTTPError(data['message'], request=None, response=response)

    return data['data']


def run_submit(tpr_path: Path) -> dict:
    '''
    Submit a TPR to get tuned.

    :param tpr_path: The .tpr file for the simulation to be tuned.
    :return: The response from the tuner.
    :raise FileNotFoundError: If the TPR file does not exist.
    :raise HTTPError: If the request fails.
    '''
    with open(tpr_path, 'rb') as f:
        files = {'file': f}
        response = requests.post(f'{TUNER_URL}/tuner_runs', files=files, auth=AUTH)
    return get_tuner_response_data(response)


def poll_status(job_id: str) -> dict:
    '''
    Poll the status of a submitted job.

    :param run_id: The ID of the job to poll.
    :return: The response from the tuner.
    :raise HTTPError: If the request fails.
    '''
    response = requests.get(f'{TUNER_URL}/tuner_runs/{job_id}/status', auth=AUTH)
    return get_tuner_response_data(response)


def delete_job(job_id: str) -> dict:
    '''
    Delete a submitted job.

    :param run_id: The ID of the job to delete.
    :return: The response from the tuner.
    :raise HTTPError: If the request fails.
    '''
    response = requests.delete(f'{TUNER_URL}/tuner_runs/{job_id}', auth=AUTH)
    return get_tuner_response_data(response)


# DEMO
if __name__ == '__main__':
    tpr_path = Path('private/md.tpr')

    # Submit a job
    response = run_submit(tpr_path)
    print('Submitted job:', response)

    print('Waiting for job to start...')
    from time import sleep
    sleep(2)

    # Poll the status
    run_id = response['tuner_run_id']
    status = poll_status(run_id)
    print('Job status:', status)

    # Delete the job
    delete_response = delete_job(run_id)
    print('Deleted job:', delete_response)
