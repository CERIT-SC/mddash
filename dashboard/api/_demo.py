"""
This is just the demo version of the API. It just returns hardcoded responses.

I mainly use it to develop the frontend.
"""

from flask import Flask, Blueprint, request, send_from_directory, Response
from flask_cors import CORS
from urllib.parse import urlencode
import requests

bp = Blueprint('dash', __name__)
CORS(bp)

demo_experiments = [
    {
        'id': 'aaaaa',
        'name': 'Cancer Cure',
        'status': 'setup',
        'step': 0,
        'token': '2f2be97e-15db-4cb4-8ef7-905efe5a4968',
    },
    {
        'id': 'bbbbb',
        'name': 'hokus pokus there is pizza on your focus',
        'status': 'setup',
        'step': 3,
        'token': '191eb452-5505-4328-9004-99eb1b0d570a',
    },
    {
        'id': 'ccccc',
        'name': 'My first experiment',
        'status': 'setup',
        'step': 5,
        'token': '2578b922-7b12-49d0-8962-b2d79afda1dc',
    },
]

notebook_running = False


@bp.route('/api/experiments', methods=['GET'])
def list_experiments():
    return {'status': 'success', 'data': demo_experiments}


@bp.route('/api/experiments/<experiment_id>', methods=['GET'])
def get_experiment(experiment_id):
    return {'status': 'success', 'data': next(e for e in demo_experiments if e['id'] == experiment_id)}


@bp.route('/api/experiments', methods=['POST'])
def create_experiment():
    return {'status': 'success', 'message': 'Experiment created.', 'data': demo_experiments[0]}


@bp.route('/api/experiments/<experiment_id>', methods=['DELETE'])
def delete_experiment(experiment_id):
    return {'status': 'success', 'message': 'Experiment deleted.'}


@bp.route('/api/experiments/<experiment_id>/notebook', methods=['POST'])
def create_notebook(experiment_id):
    global notebook_running
    notebook_running = True
    return {'status': 'success', 'message': 'Notebook created.'}


@bp.route('/api/experiments/<experiment_id>/notebook', methods=['DELETE'])
def delete_notebook(experiment_id):
    global notebook_running
    notebook_running = False
    return {'status': 'success', 'message': 'Notebook deleted.'}


@bp.route('/api/experiments/<experiment_id>/notebook', methods=['GET'])
def get_notebook(experiment_id):
    return {'status': 'success', 'message': 'up' if notebook_running else 'down', 'path': '/__BASE_PATH__/'}

tuner_running = False
tuner_demo_status = {
    'tuner_run_id': '6bec87ce-6f0c-4f8c-9572-426a1c62f44d',
    'summary': {
        'RUNNING': 2,
        'PENDING': 0,
        'TERMINATED': 1,
        'ERROR': 0
    },
    'trials': [
        {
            'id': 'e5167_00000',
            'status': 'RUNNING',
            'np': 2,
            'ntomp': 2,
            'nb': 'cpu',
            'pme': 'cpu',
            'performance': None
        },
        {
            'id': 'e5167_00002',
            'status': 'TERMINATED',
            'np': 8,
            'ntomp': 1,
            'nb': 'gpu',
            'pme': 'cpu',
            'performance': 70.158
        },
        {
            'id': 'e5167_00001',
            'status': 'RUNNING',
            'np': 2,
            'ntomp': 8,
            'nb': 'cpu',
            'pme': 'cpu',
            'performance': None
        }
    ],
    'cluster_resources': '32/32 CPUs, 0/1 GPUs used'
}


@bp.route('/api/experiments/<experiment_id>/tuner', methods=['POST'])
def submit_tuner(experiment_id):
    global tuner_running
    tuner_running = True
    return {'status': 'success', 'message': 'Tuner submitted.'}


@bp.route('/api/experiments/<experiment_id>/tuner', methods=['GET'])
def get_tuner_status(experiment_id):
    global tuner_running
    if tuner_running:
        return {'status': 'success', 'message': 'up', 'status': tuner_demo_status}
    else:
        return {'status': 'success', 'message': 'down', 'status': None}


@bp.route('/api/experiments/<experiment_id>/tuner', methods=['DELETE'])
def delete_tuner(experiment_id):
    global tuner_running
    tuner_running = False
    return {'status': 'success', 'message': 'Tuner deleted.'}



if __name__ == '__main__':
    app = Flask(__name__)
    app.register_blueprint(bp)
    app.run(debug=True, host='0.0.0.0', port=8888)
