import requests
from pathlib import Path

MDREPO_URL = 'https://mdrepo.eu/api'


def login(email: str, password: str) -> str:
    '''
    Login to the MDRepo server and return the token.
    
    :param email: Email address
    :param password: Password
    :return: Session cookie
    :raise ValueError: If the login fails
    :raise KeyError: If the session cookie is not found in the response
    '''
    data = {
        'email': email,
        'password': password
    }
    response = requests.post(f'{MDREPO_URL}/login', json=data)

    if response.status_code >= 400:
        raise ValueError(
            f"Failed to login: {response.status_code} - {response.text}")

    return response.cookies['session']


def create_experiment(session: str, community: str, metadata: dict) -> dict:
    '''
    Create a new experiment in MDRepo.
    
    :param session: Session cookie from login
    :param community: Community name
    :param metadata: Metadata for the experiment
    :return: Server response
    :raise ValueError: If the experiment creation fails
    '''
    cookies = {'session': session}
    json = {
        'files': {'enabled': True},
        'parent': {
            'communities': {'default': community}
        },
        'metadata': metadata,
    }

    response = requests.post(
        f'{MDREPO_URL}/experiments', json=json, cookies=cookies)

    if response.status_code >= 400:
        raise ValueError(
            f"Failed to create experiment: {response.status_code} - {response.text}")

    return response.json()


def upload_file(session: str, experiment_id: str, file: Path) -> dict:
    '''
    Upload a file to an experiment in MDRepo.
    
    :param session: Session cookie from login
    :param experiment_id: Experiment ID in MDRepo
    :param file: Path to the file to upload
    :return: Server response
    :raise ValueError: If the file upload fails
    '''
    cookies = {'session': session}

    # set file metadata
    json = [{'key': file.name}]
    response = requests.post(
        f'{MDREPO_URL}/experiments/{experiment_id}/draft/files',
        cookies=cookies,
        json=json,
    )

    if not response.ok:
        raise ValueError(f"Failed to set file metadata: {response.status_code} - {response.text}")

    # upload the file
    with open(file, 'rb') as f:
        response = requests.put(
            f'{MDREPO_URL}/experiments/{experiment_id}/draft/files/{file.name}/content',
            cookies=cookies,
            data=f,
            stream=True
        )

    if not response.ok:
        raise ValueError(f"Failed to upload file: {response.status_code} - {response.text}")

    # commit the file
    response = requests.post(
        f'{MDREPO_URL}/experiments/{experiment_id}/draft/files/{file.name}/commit',
        cookies=cookies
    )

    if not response.ok:
        raise ValueError(f"Failed to commit file: {response.status_code} - {response.text}")

    return response.json()
