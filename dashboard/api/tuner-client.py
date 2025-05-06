import requests
from pathlib import Path


TUNER_URL = 'https://gromacs-tuner.dyn.cloud.e-infra.cz/api'


def run_submit(tpr_path: Path, tuning_options: dict | None = None) -> dict:
    '''
    Submit an experiment to the tuner.

    :param tpr_path: The .tpr file for the simulation to be tuned.
    :param tuning_options: Optional constraints for tuning (e.g., CPU range, memory, DD, OMP).
                           This is an open-ended JSON object, and its structure may evolve.
                           NOTE: It currently seems to do nothing.
    :return: The response from the tuner.
    '''
    data = {}
    if tuning_options:
        data['tuning_options'] = tuning_options

    with open(tpr_path, 'rb') as f:
        files = {'file': f}
        response = requests.post(
            f'{TUNER_URL}/tuner_runs', files=files, data=data)

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


# DEPRECATED
# def get_results(run_id: str) -> dict:
#     '''
#     Get the results of a completed job.

#     :param run_id: The ID of the job to get results for.
#     :return: The response from the tuner.
#     '''
#     response = requests.get(f'{TUNER_URL}/tuner_runs/{run_id}/results')
#     response.raise_for_status()
#     return response.json()


# DEMO
if __name__ == '__main__':
    tpr_path = Path('private/md.tpr')

    # NOTE: these options are probably wrong
    tunning_options = {
        'pme': "cpu",
        'nb': "gpu",
        'np': [1, 4],
        'ntomp': [1, 2, 4],
    }

    # # Submit a job
    response = run_submit(tpr_path, tunning_options)
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
