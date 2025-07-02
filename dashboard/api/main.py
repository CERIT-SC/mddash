import os
from flask import Flask, Blueprint, request, send_file, abort
from dataclasses import asdict


from config import STATE_FILE, PREFIX, NAMESPACE, NOTEBOOK_IMAGE, DATA_DIR
from experiment import Experiment
from state import Experiments
from gromacs_job import GromacsJob
from api_response import ApiResponse
from utils import get_files_with_extension
import mdrepo_client
import caddy_client
import tuner_client

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


# ----- HEALTH CHECK -----

@bp.route('/api/')
def index():
    return ApiResponse.success('Welcome to the Dashboard API!')


@bp.route('/api/metrics', methods=['GET'])
def get_metrics():
    metrics = get_namespace_resource_allocation(NAMESPACE)
    return ApiResponse.success(metrics)


# ----- EXPERIMENTS -----

@bp.route('/api/experiments', methods=['GET'])
def list_experiments():
    try:
        return ApiResponse.success(experiments.get_all())
    except Exception as e:
        return ApiResponse.error(str(e))


@bp.route('/api/experiments/<experiment_id>', methods=['GET'])
def get_experiment(experiment_id):
    try:
        return ApiResponse.success(experiments.get(experiment_id))
    except Exception as e:
        return ApiResponse.error(str(e))


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
                return ApiResponse.error('Invalid experiment type or missing data.')

        experiments.add(experiment)
        experiments.save(STATE_FILE)
        return ApiResponse.success(asdict(experiment))

    except Exception as e:
        return ApiResponse.error(str(e))


@bp.route('/api/experiments/<experiment_id>', methods=['DELETE'])
def delete_experiment(experiment_id):
    try:
        experiments.remove(experiment_id)
        experiments.save(STATE_FILE)
        delete_notebook(experiment_id)
        return ApiResponse.success()
    except Exception as e:
        return ApiResponse.error(str(e))


# ----- NOTEBOOK -----

# TODO: delete it one day (or not idk, can we spawn notebooks with jupyterhub?)
@bp.route('/api/experiments/<experiment_id>/notebook', methods=['POST'])
def start_notebook(experiment_id):
    try:
        token = experiments.get(experiment_id).token
        create_notebook_pod(NOTEBOOK_IMAGE, NAMESPACE, experiment_id, f'{PREFIX}/notebook/{experiment_id}', token)
        create_notebook_service(NAMESPACE, experiment_id)

        route_id = caddy_client.add_proxy_route(
            path=f'/notebook/{experiment_id}/*',
            upstream=f'svc-{experiment_id}.{NAMESPACE}.svc.cluster.local:80',
            route_id=f'route-{experiment_id}-notebook',
        )
        if route_id is None:
            return ApiResponse.error('Failed to create connection to notebook.')

        return ApiResponse.success({
            'up': True,
            'path': f'{PREFIX}/notebook/{experiment_id}/?token={token}'
        })
    except Exception as e:
        return ApiResponse.error(str(e))


@bp.route('/api/experiments/<experiment_id>/notebook', methods=['DELETE'])
def delete_notebook(experiment_id):
    try:
        delete_notebook_pod(NAMESPACE, experiment_id)
        delete_notebook_service(NAMESPACE, experiment_id)

        if not caddy_client.remove_route(f'route-{experiment_id}-notebook'):
            print('Failed to remove route from Caddy.')

        return ApiResponse.success()
    except Exception as e:
        return ApiResponse.error(str(e))


@bp.route('/api/experiments/<experiment_id>/notebook', methods=['GET'])
def get_notebook(experiment_id):
    try:
        token = experiments.get(experiment_id).token
        is_up = ping_resource('svc', f'svc-{experiment_id}', NAMESPACE)
        return ApiResponse.success({
            'up': is_up,
            'path': f'{PREFIX}/notebook/{experiment_id}/?token={token}'
        })
    except Exception as e:
        return ApiResponse.error(str(e))


# ----- TUNER -----

@bp.route('/api/experiments/<experiment_id>/tuner/<tpr_name>', methods=['POST'])
def submit_tuner(experiment_id, tpr_name):
    try:
        experiment = experiments.get(experiment_id)
        tpr_path = DATA_DIR / experiment_id / tpr_name

        if not tpr_name.endswith('.tpr'):
            return ApiResponse.error("TPR file must have a '.tpr' extension.")

        if not tpr_path.exists():
            return ApiResponse.error(f"TPR file '{tpr_name}' not found.")

        # if the job already exists, return that job
        if experiment.tuner_jobs.get(tpr_name):
            return ApiResponse.success(experiment.tuner_jobs[tpr_name])

        # Submit the TPR file to the tuner
        data = tuner_client.run_submit(tpr_path)
        experiment.tuner_jobs[tpr_name] = data
        experiments.save(STATE_FILE)

        return ApiResponse.success(data)

    except Exception as e:
        return ApiResponse.error(str(e))


@bp.route('/api/experiments/<experiment_id>/tuner', methods=['GET'])
def get_tuner_statuses(experiment_id):
    try:
        experiment = experiments.get(experiment_id)
        tuner_statuses = {}

        for tpr_name, job in experiment.tuner_jobs.items():
            status = tuner_client.poll_status(job['tuner_run_id'])
            tuner_statuses[tpr_name] = status

        experiment.tuner_jobs = tuner_statuses
        experiments.save(STATE_FILE)

        return ApiResponse.success(tuner_statuses)

    except Exception as e:
        return ApiResponse.error(str(e))


@bp.route('/api/experiments/<experiment_id>/tuner/<tpr_name>', methods=['GET'])
def get_tuner_status(experiment_id, tpr_name):
    try:
        experiment = experiments.get(experiment_id)
        job = experiment.tuner_jobs.get(tpr_name)

        if not job:
            return ApiResponse.error(f"Tune job for '{tpr_name}' not found.")

        status = tuner_client.poll_status(job['tuner_run_id'])
        experiment.tuner_jobs[tpr_name] = status
        experiments.save(STATE_FILE)
        
        return ApiResponse.success(status)

    except Exception as e:
        return ApiResponse.error(str(e))


@bp.route('/api/experiments/<experiment_id>/tuner/<tpr_name>', methods=['DELETE'])
def delete_tuner(experiment_id, tpr_name):
    try:
        experiment = experiments.get(experiment_id)
        job = experiment.tuner_jobs.pop(tpr_name, None)

        if not job:
            return ApiResponse.error(f"Tune job for '{tpr_name}' not found.")

        tuner_client.delete_job(job['tuner_run_id'])
        experiments.save(STATE_FILE)

        return ApiResponse.success()

    except Exception as e:
        return ApiResponse.error(str(e))


# ----- GROMACS -----

@bp.route('/api/experiments/<experiment_id>/gmx/<tpr_name>', methods=['POST'])
def submit_gmx(experiment_id, tpr_name):
    try:
        experiment = experiments.get(experiment_id)
        tpr_path = DATA_DIR / experiment_id / tpr_name

        if not tpr_name.endswith('.tpr'):
            return ApiResponse.error("TPR file must have a '.tpr' extension.")

        if not tpr_path.exists():
            return ApiResponse.error(f"TPR file '{tpr_name}' not found.")

        # if the job already exists, return that job
        if experiment.gromacs_jobs.get(tpr_name):
            return ApiResponse.error("Gromacs job already exists for this TPR file.")

        # Submit the TPR file to Gromacs
        job = GromacsJob(
            id=tpr_name, # TODO: do we need an ID?
            pme=request.form['pme'],
            nb=request.form['nb'],
            np=request.form['np'],
            ntomp=request.form['ntomp'],
            extra_args=request.form['extra_args'],
        )
        experiment.gromacs_jobs[tpr_name] = job
        experiments.save(STATE_FILE)

        return ApiResponse.success(job)
    except Exception as e:
        return ApiResponse.error(str(e))


@bp.route('/api/experiments/<experiment_id>/gmx', methods=['GET'])
def get_gmx_statuses(experiment_id):
    try:
        experiment = experiments.get(experiment_id)
        gmx_statuses = {}

        for tpr_name, job in experiment.gromacs_jobs.items():
            job.poll_status()
            gmx_statuses[tpr_name] = asdict(job)

        experiments.save(STATE_FILE)

        return ApiResponse.success(gmx_statuses)

    except Exception as e:
        return ApiResponse.error(str(e))


@bp.route('/api/experiments/<experiment_id>/gmx/<tpr_name>', methods=['GET'])
def get_gmx_status(experiment_id, tpr_name):
    try:
        experiment = experiments.get(experiment_id)
        job = experiment.gromacs_jobs.get(tpr_name)

        if not job:
            return ApiResponse.error(f"Gromacs job for '{tpr_name}' not found.")

        job.poll_status()
        experiments.save(STATE_FILE)

        return ApiResponse.success(asdict(job))

    except Exception as e:
        return ApiResponse.error(str(e))


@bp.route('/api/experiments/<experiment_id>/gmx/<tpr_name>', methods=['DELETE'])
def delete_gmx(experiment_id, tpr_name):
    try:
        experiment = experiments.get(experiment_id)
        job = experiment.gromacs_jobs.pop(tpr_name, None)  # TODO: maybe keep the job?

        if not job:
            return ApiResponse.error(f"Gromacs job for '{tpr_name}' not found.")

        job.stop()
        experiments.save(STATE_FILE)

        return ApiResponse.success()

    except Exception as e:
        return ApiResponse.error(str(e))


# ----- PUBLISHING -----

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

        return ApiResponse.success(mdrepo_experiment)

    except Exception as e:
        return ApiResponse.error(str(e))


# ----- FILES -----

@bp.route('/api/experiments/<experiment_id>/files', methods=['GET'])
def list_experiment_files(experiment_id):
    try:
        extension = request.args.get('ext', '').lower()

        files = get_files_with_extension(DATA_DIR / experiment_id, extension)
        # add URLs to file list
        for f in files:
            f['url'] = f'{PREFIX}/api/experiments/{experiment_id}/files/{f["name"]}'

        return ApiResponse.success(files)

    except Exception as e:
        return ApiResponse.error(str(e))


@bp.route('/api/experiments/<experiment_id>/files/<path:path>', methods=['GET'])
def get_experiment_file(experiment_id, path):
    file_path = DATA_DIR / experiment_id / path

    # prevent path traversal
    if not str(file_path.resolve()).startswith(str((DATA_DIR / experiment_id).resolve())):
        abort(403)

    # Check if file exists and is a file
    if not file_path.exists() or not file_path.is_file():
        abort(404)

    return send_file(file_path, as_attachment=False)


app = Flask(__name__)
app.register_blueprint(bp)


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
