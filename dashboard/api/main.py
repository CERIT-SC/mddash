# vim: set ai ts=4 expandtab nomouse:

import os
from flask import Flask, Blueprint, request, send_file, abort
from dataclasses import asdict


from config import STATE_FILE, PREFIX, NAMESPACE, NOTEBOOK_IMAGE, DATA_DIR
from experiment import Experiment
from state import Experiments
import mdrepo_client
import caddy_client

from k8s import (
    create_notebook_pod,
    create_notebook_service,
    delete_notebook_pod,
    delete_notebook_service,
    ping_resource, 
    get_namespace_resource_allocation
)


experiments = Experiments.load(STATE_FILE)

bp = Blueprint('dash', __name__)


@bp.route('/api/')
def index():
    return {'status': 'success', 'message': 'FAIR MD Dashboard API'}


@bp.route('/api/experiments', methods=['GET'])
def list_experiments():
    try:
        return {'status': 'success', 'data': experiments.get_all()}
    except Exception as e:
        return {'status': 'error', 'message': str(e)}


@bp.route('/api/experiments/<experiment_id>', methods=['GET'])
def get_experiment(experiment_id):
    try:
        return {'status': 'success', 'data': experiments.get(experiment_id)}
    except Exception as e:
        return {'status': 'error', 'message': str(e)}


@bp.route('/api/experiments', methods=['POST'])
def create_experiment():
    form = request.form

    try:
        name = form['experiment-name']
        pdb_id = form.get('pdb-id', 'XXX:fake')
        repo_url = form.get('repo-url')
        simulation_file = request.files.get('simulation-file')

        app.logger.debug(f'{request.form}')
        match form['type']:
            case 'pdb' if pdb_id:
                experiment = Experiment.from_pdb(name, pdb_id)
            case 'repo' if repo_url:
                experiment = Experiment.from_repo(name, repo_url)
            case 'file' if simulation_file:
                experiment = Experiment.from_tpr(name, simulation_file)
            case _:
                return {'status': 'error', 'message': 'Invalid experiment type or missing data.'}

        experiments.add(experiment)
        experiments.save(STATE_FILE)
        return {'status': 'success', 'message': 'Experiment created.', 'data': asdict(experiment)}

    except Exception as e:
        return {'status': 'error', 'message': str(e)}


@bp.route('/api/experiments/<experiment_id>', methods=['DELETE'])
def delete_experiment(experiment_id):
    try:
        experiments.remove(experiment_id)
        experiments.save(STATE_FILE)
        delete_notebook(experiment_id)
        return {'status': 'success', 'message': 'Experiment deleted.'}

    except Exception as e:
        return {'status': 'error', 'message': str(e)}


# TODO: delete it one day
@bp.route('/api/experiments/<experiment_id>/notebook', methods=['POST'])
def start_notebook(experiment_id):
    create_notebook_pod(NOTEBOOK_IMAGE, NAMESPACE, experiment_id, f'{PREFIX}/notebook/{experiment_id}', experiments.get(experiment_id).token)
    create_notebook_service(NAMESPACE, experiment_id)

    route_id = caddy_client.add_proxy_route(
        path=f'/notebook/{experiment_id}/*',
        upstream=f'svc-{experiment_id}.{NAMESPACE}.svc.cluster.local:80',
        route_id=f'route-{experiment_id}',
    )
    if route_id is None:
        return {'status': 'error', 'message': 'Failed to create connection to notebook.'}

    # TODO: store route_id

    return {'status': 'success', 'message': 'Notebook created.'}


@bp.route('/api/experiments/<experiment_id>/notebook', methods=['DELETE'])
def delete_notebook(experiment_id):
    delete_notebook_pod(NAMESPACE, experiment_id)
    delete_notebook_service(NAMESPACE, experiment_id)
    if not caddy_client.remove_route(f'route-{experiment_id}'):
        print('Failed to remove route from Caddy.')
    return {'status': 'success', 'message': 'Notebook deleted.'}


@bp.route('/api/experiments/<experiment_id>/notebook', methods=['GET'])
def get_notebook(experiment_id):
    token = experiments.get(experiment_id).token

    try:
        is_up = ping_resource('svc', f'svc-{experiment_id}', NAMESPACE)
        return {'status': 'success', 'message': 'up' if is_up else 'down', 'path': f'{PREFIX}/notebook/{experiment_id}/?token={token}'}

    except Exception as e:
        return {'status': 'error', 'message': str(e)}


@bp.route('/api/experiments/<experiment_id>/publish', methods=['GET'])
def publish_experiment(experiment_id):
    
    # TODO: figure out how this value gets here
    community = 'ceitec'

    try:
        experiment = experiments.get(experiment_id)
        session = mdrepo_client.login('test@test.com', '123456')  # TODO: once mdrepo supports our auth, use its token here

        metadata = {
            "simulations:": [],
        }

        # create experiment in MDRepo
        mdrepo_experiment = mdrepo_client.create_experiment(session, community, metadata)
        experiment.mdrepo_id = mdrepo_experiment['id']
        experiments.save(STATE_FILE)

        # upload files to MDRepo
        for file in os.listdir(DATA_DIR / experiment_id):
            file_path = os.path.join(DATA_DIR / experiment_id, file)
            mdrepo_client.upload_file(session, experiment.mdrepo_id, file_path)

        return {'status': 'success', 'message': 'Experiment created.', 'data': mdrepo_experiment}

    except Exception as e:
        return {'status': 'error', 'message': str(e)}


@bp.route('/api/metrics', methods=['GET'])
def get_metrics():
    metrics = get_namespace_resource_allocation(NAMESPACE)
    return {'status': 'success', 'data': metrics}


@bp.route('/api/experiments/<experiment_id>/files', methods=['GET'])
def list_experiment_files(experiment_id):
    try:
        extension = request.args.get('ext', '').lower()
        experiment_dir = DATA_DIR / experiment_id
        
        if not experiment_dir.exists():
            return {'status': 'error', 'message': 'Experiment not found.'}

        files = []
        for file_path in experiment_dir.iterdir():
            if not file_path.is_file() or extension and not file_path.name.lower().endswith(f'.{extension}'):
                continue

            # Create the file URL
            file_url = f"/experiments/{experiment_id}/files/{file_path.name}"
            files.append({
                'name': file_path.name,
                'url': file_url,
                'size': file_path.stat().st_size
            })

        return {'status': 'success', 'data': files}

    except Exception as e:
        return {'status': 'error', 'message': str(e)}


@bp.route('/api/experiments/<experiment_id>/files/<path:path>', methods=['GET'])
def get_experiment_file(experiment_id, path):
    try:
        file_path = DATA_DIR / experiment_id / path

        # prevent path traversal
        if not str(file_path.resolve()).startswith(str((DATA_DIR / experiment_id).resolve())):
            abort(403)

        # Check if file exists and is a file
        if not file_path.exists() or not file_path.is_file():
            abort(404)

        return send_file(file_path, as_attachment=False)

    except Exception as e:
        return {'status': 'error', 'message': str(e)}


app = Flask(__name__)
app.register_blueprint(bp)


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
