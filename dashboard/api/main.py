import os
import logging
from flask import Flask, Blueprint, request, send_file, abort
from dataclasses import asdict

from config import STATE_FILE, PREFIX, NAMESPACE, NOTEBOOK_IMAGE, DATA_DIR, PVC_NAME
from experiment import Experiment
from state import Experiments
from gromacs_job import GromacsJob, DeviceType
from dashboard.api.api_response import ApiResponse
from utils import get_files_with_extension
import dashboard.api.clients.mdrepo as mdrepo
import dashboard.api.clients.caddy as caddy
import dashboard.api.clients.tuner as tuner_client
from enums.pod_status import PodStatus
from dashboard.api.clients.k8s import (
    create_notebook_pod,
    create_service,
    delete_pod,
    delete_service,
    get_pod_status,
    get_namespace_resource_allocation
)


logger = logging.getLogger(__name__)
experiments = Experiments.load(STATE_FILE)

# Create blueprint with URL prefix
bp = Blueprint('dash', __name__, url_prefix=PREFIX)


# ----- HEALTH CHECK -----

@bp.route('/api/')
def index():
    return ApiResponse.success('Welcome to the Dashboard API!')


@bp.route('/api/metrics', methods=['GET'])
def get_metrics():
    try:
        metrics = get_namespace_resource_allocation(NAMESPACE)
        return ApiResponse.success(metrics)
    except Exception as e:
        return ApiResponse.error(str(e), exc_info=True)


# ----- EXPERIMENTS -----

@bp.route('/api/experiments', methods=['GET'])
def list_experiments():
    try:
        return ApiResponse.success(experiments.get_all())
    except Exception as e:
        return ApiResponse.error(str(e), exc_info=True)


@bp.route('/api/experiments/<experiment_id>', methods=['GET'])
def get_experiment(experiment_id):
    try:
        return ApiResponse.success(experiments.get(experiment_id))
    except Exception as e:
        return ApiResponse.error(str(e), exc_info=True)


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
        return ApiResponse.error(str(e), exc_info=True)


@bp.route('/api/experiments/<experiment_id>', methods=['DELETE'])
def delete_experiment(experiment_id):
    try:
        experiments.remove(experiment_id)
        experiments.save(STATE_FILE)
        delete_notebook(experiment_id)
        return ApiResponse.success()
    except Exception as e:
        return ApiResponse.error(str(e), exc_info=True)


# ----- NOTEBOOK -----

# TODO: delete it one day (or not idk, can we spawn notebooks with jupyterhub?)
@bp.route('/api/experiments/<experiment_id>/notebook', methods=['POST'])
def start_notebook(experiment_id):
    try:
        token = experiments.get(experiment_id).token
        pod_name = f'notebook-{experiment_id}'
        svc_name = f'svc-{experiment_id}'

        try:
            create_notebook_pod(NOTEBOOK_IMAGE, NAMESPACE, PVC_NAME, pod_name, experiment_id, f'{PREFIX}/notebook/{experiment_id}', token)
        except Exception as e:
            return ApiResponse.error(f'Failed to create notebook pod: {str(e)}', exc_info=True)
        
        try:
            create_service(NAMESPACE, svc_name, pod_name)
        except Exception as e:
            delete_pod(NAMESPACE, pod_name)
            return ApiResponse.error(f'Failed to create notebook service: {str(e)}', exc_info=True)

        route_id = caddy.add_proxy_route(
            path=f'{PREFIX}/notebook/{experiment_id}',
            upstream=f'{svc_name}.{NAMESPACE}.svc.cluster.local:80',
            route_id=f'route-{experiment_id}-notebook',
        )
        if route_id is None:
            delete_pod(NAMESPACE, pod_name)
            delete_service(NAMESPACE, svc_name)
            return ApiResponse.error('Failed to create proxy connection to notebook.')

        return ApiResponse.success({
            'status': str(PodStatus.PENDING),
            'path': f'{PREFIX}/notebook/{experiment_id}/?token={token}'
        })
    except Exception as e:
        return ApiResponse.error(str(e), exc_info=True)


@bp.route('/api/experiments/<experiment_id>/notebook', methods=['DELETE'])
def delete_notebook(experiment_id):
    try:
        pod_name = f'notebook-{experiment_id}'
        svc_name = f'svc-{experiment_id}'
        route_id = f'route-{experiment_id}-notebook'

        try:
            delete_pod(NAMESPACE, pod_name)
        except Exception as e:
            logger.error(f'Failed to delete notebook pod:', exc_info=True)

        try:
            delete_service(NAMESPACE, svc_name)
        except Exception as e:
            logger.error(f'Failed to delete notebook service:', exc_info=True)

        if not caddy.remove_route(route_id):
            logger.error('Failed to remove route from Caddy.')

        return ApiResponse.success()
    except Exception as e:
        return ApiResponse.error(str(e), exc_info=True)


@bp.route('/api/experiments/<experiment_id>/notebook', methods=['GET'])
def get_notebook(experiment_id):
    try:
        experiment = experiments.get(experiment_id)
        token = experiment.token
        pod_name = f'notebook-{experiment_id}'

        try:
            experiment.notebook_status = get_pod_status(NAMESPACE, pod_name)
        except Exception as e:
            logger.error(f'Failed to get notebook pod status:', exc_info=True)
            experiment.notebook_status = PodStatus.UNKNOWN

        experiments.save(STATE_FILE)

        return ApiResponse.success({
            'status': str(experiment.notebook_status),
            'path': f'{PREFIX}/notebook/{experiment_id}/?token={token}'
        })
    except Exception as e:
        return ApiResponse.error(str(e), exc_info=True)


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
        return ApiResponse.error(str(e), exc_info=True)


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
        return ApiResponse.error(str(e), exc_info=True)


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
        return ApiResponse.error(str(e), exc_info=True)


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
        return ApiResponse.error(str(e), exc_info=True)


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
            experiment_id=experiment_id,
            tpr_name=tpr_name,
            pme=DeviceType.from_string(request.form['pme']),
            nb=DeviceType.from_string(request.form['nb']),
            np=int(request.form['np']),
            ntomp=int(request.form['ntomp']),
            extra_args=request.form.get('extra_args', ''),
        )
        job.start()

        experiment.gromacs_jobs[tpr_name] = job
        experiments.save(STATE_FILE)

        return ApiResponse.success(job)
    except Exception as e:
        return ApiResponse.error(str(e), exc_info=True)


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
        return ApiResponse.error(str(e), exc_info=True)


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
        return ApiResponse.error(str(e), exc_info=True)


@bp.route('/api/experiments/<experiment_id>/gmx/<tpr_name>', methods=['DELETE'])
def delete_gmx(experiment_id, tpr_name):
    try:
        experiment = experiments.get(experiment_id)
        job = experiment.gromacs_jobs.pop(tpr_name, None)  # TODO: maybe keep the job?

        if not job:
            return ApiResponse.error(f"Gromacs job for '{tpr_name}' not found.")

        job.delete()
        experiments.save(STATE_FILE)

        return ApiResponse.success()

    except Exception as e:
        return ApiResponse.error(str(e), exc_info=True)


@bp.route('/api/experiments/<experiment_id>/gmx/<tpr_name>/log', methods=['GET'])
def get_gmx_log(experiment_id, tpr_name):
    try:
        experiment = experiments.get(experiment_id)
        job = experiment.gromacs_jobs.get(tpr_name)

        if not job:
            return ApiResponse.error(f"Gromacs job for '{tpr_name}' not found.")
        
        log_type = request.args.get('type', 'gmx').lower()
        tail_lines = request.args.get('tail', '10000')

        if log_type not in ['gmx', 'stdout', 'stderr']:
            return ApiResponse.error("Invalid log type. Use 'gmx', 'stdout', or 'stderr'.")

        if not tail_lines.isdigit():
            return ApiResponse.error("Tail lines must be a positive integer.")

        log = job.get_log(log_type, int(tail_lines))
        return ApiResponse.success(log)

    except Exception as e:
        return ApiResponse.error(str(e), exc_info=True)


# ----- PUBLISHING -----

@bp.route('/api/experiments/<experiment_id>/publish', methods=['GET'])
def publish_experiment(experiment_id):
    
    # TODO: figure out how this value gets here
    community = 'ceitec'

    try:
        experiment = experiments.get(experiment_id)
        session = mdrepo.login('test@test.com', '123456')  # TODO: once mdrepo supports our auth, use its token here

        metadata = {
            "simulations:": [],
        }

        # create experiment in MDRepo
        mdrepo_experiment = mdrepo.create_experiment(session, community, metadata)
        experiment.mdrepo_id = mdrepo_experiment['id']
        experiments.save(STATE_FILE)

        # upload files to MDRepo
        for file in os.listdir(DATA_DIR / experiment_id):
            file_path = os.path.join(DATA_DIR / experiment_id, file)
            mdrepo.upload_file(session, experiment.mdrepo_id, file_path)

        return ApiResponse.success(mdrepo_experiment)

    except Exception as e:
        return ApiResponse.error(str(e), exc_info=True)


# ----- FILES -----

@bp.route('/api/experiments/<experiment_id>/files', methods=['GET'])
def list_experiment_files(experiment_id):
    try:
        ext_param = request.args.get('ext', '').lower()
        extensions = [ext.strip() for ext in ext_param.split(',') if ext.strip()]
        files = get_files_with_extension(DATA_DIR / experiment_id, extensions)
        # add URLs to file list
        for f in files:
            f['url'] = f'{PREFIX}/api/experiments/{experiment_id}/files/{f["name"]}'

        return ApiResponse.success(files)

    except Exception as e:
        return ApiResponse.error(str(e), exc_info=True)


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
