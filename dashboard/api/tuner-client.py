import requests
from pathlib import Path


TUNER_URL = 'https://gromacs-tuner.dyn.cloud.e-infra.cz/api'


def run_submit(tpr_path: Path) -> dict:
    '''
    Submit an experiment to the tuner.

    :param experiment_id: The ID of the experiment to submit.
    :return: The response from the tuner.
    '''
    with open(tpr_path, 'rb') as f:
        files = {'file': f}
        response = requests.post(f'{TUNER_URL}/tuner_runs', files=files)

    response.raise_for_status()
    return response.json()


def poll_status(run_id: str) -> dict:
    '''
    Poll the status of a submitted job.

    :param run_id: The ID of the job to poll.
    :return: The response from the tuner.
    '''
    response = requests.get(f'{TUNER_URL}/tuner_runs/{run_id}/status')
    response.raise_for_status()
    return response.json()


def delete_job(run_id: str) -> dict:
    '''
    Delete a submitted job.

    :param run_id: The ID of the job to delete.
    :return: The response from the tuner.
    '''
    response = requests.delete(f'{TUNER_URL}/tuner_runs/{run_id}')
    response.raise_for_status()
    return response.json()
