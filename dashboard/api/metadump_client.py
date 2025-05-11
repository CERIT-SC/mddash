import requests
import time


METADUMP_URL = 'https://gmxmetadump.biodata.ceitec.cz/api'  # old api
GMD_URL = 'https://gmd.ceitec.cz/api'   # new api


def annotate(trp_path: str) -> dict:
    '''
    Annotate a .tpr file using the Metadump server.
    
    :param trp_path: Path to the .tpr file to be annotated.
    :return: The response from the Metadump server.
    :raise ValueError: If the request to the Metadump server fails.
    :raise KeyError: If the response does not contain the expected data.
    '''
    with open(trp_path, 'rb') as f:
        files = {'file': f}
        response = requests.post(f'{GMD_URL}/annotate', files=files)

    if response.status_code >= 400:
        raise ValueError(f"Failed to annotate file: {response.status_code}")

    request_id = response.json()['request_id']

    # Poll the status of the annotation
    while True:
        response = requests.get(f'{GMD_URL}/annotate/{request_id}/status')
        if response.status_code >= 400:
            raise ValueError(
                f"Failed to get annotation status: {response.status_code}")

        status = response.json()['job_metadata']['status']
        if status == 'completed':
            break
        elif status == 'error':
            raise ValueError("Annotation failed")

        time.sleep(0.2)

    return response.json()['result']
