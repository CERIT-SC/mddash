"""
API routes for demo API.
Mimics the real API endpoints and behavior.
"""

import time
import random
from http import HTTPStatus
from pathlib import Path

from flask import Blueprint, request, send_file

from api_response import ApiResponse
from state import state


bp = Blueprint('demo', __name__)


# ----- HEALTH CHECK -----

@bp.route('/api/metrics', methods=['GET'])
def get_metrics():
    """Get system metrics."""
    return ApiResponse.success({
        'requests': {
            'cpu': 768,  # millicores
            'memory': 7500000000,  # 7.5G
            'storage': 12025908429  # 11.2Gi
        },
        'limits': {
            'cpu': 2000,  # millicores
            'memory': 8000000000,  # 8G
            'storage': 107374182400  # 100Gi
        }
    })


# ----- EXPERIMENTS -----

@bp.route('/api/experiments', methods=['GET'])
def list_experiments():
    """List all experiments."""
    experiments = state.get_all_experiments()
    return ApiResponse.success(experiments)


@bp.route('/api/experiments/<experiment_id>', methods=['GET'])
def get_experiment(experiment_id: str):
    """Get single experiment by ID."""
    experiment = state.get_experiment(experiment_id)
    if not experiment:
        return ApiResponse.error(f'Experiment {experiment_id} not found', HTTPStatus.NOT_FOUND)
    return ApiResponse.success(experiment)


@bp.route('/api/experiments', methods=['POST'])
def create_experiment():
    """Create a new experiment."""
    form = request.form
    name = form.get('experiment-name', 'New Experiment')
    exp_type = form.get('type', 'file')
    
    # Generate unique 5-char ID
    exp_id = ''.join(random.choice('abcdefghijklmnopqrstuvwxyz') for _ in range(5))
    
    # Create source message based on type
    if exp_type == 'pdb':
        pdb_id = form.get('pdb-id', 'XXXX')
        source_message = f"Created by downloading PDB ID '{pdb_id}'."
        has_tpr = False
    elif exp_type == 'repo':
        repo_url = form.get('repo-url', 'https://zenodo.org/records/unknown')
        source_message = f"Created by downloading repository from '{repo_url}'."
        has_tpr = False
    else:
        file_name = request.files.get('simulation-file', type('obj', (object,), {'filename': 'unknown.tpr'})()).filename
        source_message = f"Created by uploading TPR file '{file_name}'."
        has_tpr = file_name and file_name.endswith('.tpr')
    
    # Create experiment
    experiment = state.create_experiment(exp_id, name, source_message)
    experiment['has_tpr_files'] = has_tpr
    
    return ApiResponse.success(state.get_experiment(exp_id), HTTPStatus.CREATED)


@bp.route('/api/experiments/<experiment_id>', methods=['DELETE'])
def delete_experiment(experiment_id: str):
    """Delete an experiment."""
    if not state.delete_experiment(experiment_id):
        return ApiResponse.error(f'Experiment {experiment_id} not found', HTTPStatus.NOT_FOUND)
    return ApiResponse.success(status=HTTPStatus.NO_CONTENT)


@bp.route('/api/experiments/<experiment_id>', methods=['PATCH'])
def edit_experiment(experiment_id: str):
    """Edit experiment (currently only name)."""
    experiment = state.experiments.get(experiment_id)
    if not experiment:
        return ApiResponse.error(f'Experiment {experiment_id} not found', HTTPStatus.NOT_FOUND)
    
    data = request.get_json()
    if not data:
        return ApiResponse.error('No data provided.', HTTPStatus.BAD_REQUEST)
    
    if 'name' in data:
        experiment['name'] = data['name']
        experiment['updated_at'] = time.strftime('%Y-%m-%dT%H:%M:%S')
    
    return ApiResponse.success(state.get_experiment(experiment_id))


@bp.route('/api/experiments/<experiment_id>/step', methods=['GET'])
def get_experiment_step(experiment_id: str):
    """Get experiment step."""
    experiment = state.get_experiment(experiment_id)
    if not experiment:
        return ApiResponse.error(f'Experiment {experiment_id} not found', HTTPStatus.NOT_FOUND)
    return ApiResponse.success(experiment['step'])


@bp.route('/api/experiments/<experiment_id>/publish', methods=['POST'])
def publish_experiment(experiment_id: str):
    """Publish experiment to MDRepo."""
    experiment = state.experiments.get(experiment_id)
    if not experiment:
        return ApiResponse.error(f'Experiment {experiment_id} not found', HTTPStatus.NOT_FOUND)
    
    # Simulate MDRepo response
    mdrepo_experiment = {
        "id": "xej9e-x3720",
        "created": "2025-05-11T14:24:31.964333+00:00",
        "updated": "2025-05-11T14:24:32.188250+00:00",
        "links": {
            "self_html": "https://mdrepo.eu/experiments/xej9e-x3720/preview"
        },
        "state": "draft"
    }
    
    # Update experiment (step and status will be calculated dynamically)
    experiment['mdrepo_id'] = mdrepo_experiment['id']
    
    return ApiResponse.success(mdrepo_experiment, HTTPStatus.CREATED)


# ----- NOTEBOOK -----

@bp.route('/api/experiments/<experiment_id>/notebook', methods=['GET'])
def get_notebook(experiment_id: str):
    """Get notebook status."""
    exp = state.experiments.get(experiment_id)
    if not exp:
        return ApiResponse.error(f'Experiment {experiment_id} not found', HTTPStatus.NOT_FOUND)
    
    return ApiResponse.success(state._clean_notebook(exp['notebook']))


@bp.route('/api/experiments/<experiment_id>/notebook', methods=['POST'])
def start_notebook(experiment_id: str):
    """Start notebook."""
    exp = state.experiments.get(experiment_id)
    if not exp:
        return ApiResponse.error(f'Experiment {experiment_id} not found', HTTPStatus.NOT_FOUND)
    
    notebook = exp['notebook']
    notebook['status'] = 'PENDING'
    notebook['start_time'] = time.time()
    
    return ApiResponse.success(state._clean_notebook(notebook), HTTPStatus.CREATED)


@bp.route('/api/experiments/<experiment_id>/notebook', methods=['DELETE'])
def stop_notebook(experiment_id: str):
    """Stop notebook."""
    exp = state.experiments.get(experiment_id)
    if not exp:
        return ApiResponse.error(f'Experiment {experiment_id} not found', HTTPStatus.NOT_FOUND)
    
    notebook = exp['notebook']
    notebook['status'] = 'DOWN'
    notebook['start_time'] = None
    return ApiResponse.success(status=HTTPStatus.NO_CONTENT)


# ----- TUNER -----

@bp.route('/api/experiments/<experiment_id>/tuner', methods=['GET'])
def list_tuner_jobs(experiment_id: str):
    """List all tuner jobs for experiment."""
    exp = state.experiments.get(experiment_id)
    if not exp:
        return ApiResponse.error(f'Experiment {experiment_id} not found', HTTPStatus.NOT_FOUND)
    
    tuner_jobs = [state._format_tuner_job(tj) for tj in exp['tuner_jobs']]
    return ApiResponse.success(tuner_jobs)


@bp.route('/api/experiments/<experiment_id>/tuner/<tpr_name>', methods=['GET'])
def get_tuner_job(experiment_id: str, tpr_name: str):
    """Get tuner job status."""
    exp = state.experiments.get(experiment_id)
    if not exp:
        return ApiResponse.error(f'Experiment {experiment_id} not found', HTTPStatus.NOT_FOUND)
    
    tuner = next((tj for tj in exp['tuner_jobs'] if tj['tpr_name'] == tpr_name), None)
    if not tuner:
        return ApiResponse.error(f"Tuner job for '{tpr_name}' not found.", HTTPStatus.NOT_FOUND)
    return ApiResponse.success(state._format_tuner_job(tuner))


@bp.route('/api/experiments/<experiment_id>/tuner/<tpr_name>', methods=['POST'])
def start_tuner_job(experiment_id: str, tpr_name: str):
    """Start tuner job."""
    exp = state.experiments.get(experiment_id)
    if not exp:
        return ApiResponse.error(f'Experiment {experiment_id} not found', HTTPStatus.NOT_FOUND)
    
    # Check if already exists
    existing = next((tj for tj in exp['tuner_jobs'] if tj['tpr_name'] == tpr_name), None)
    if existing:
        return ApiResponse.success(state._format_tuner_job(existing), HTTPStatus.OK)
    
    # Create new tuner job
    tuner = state._create_tuner_job(experiment_id, tpr_name, is_pending=False)
    exp['tuner_jobs'].append(tuner)
    return ApiResponse.success(state._format_tuner_job(tuner), HTTPStatus.CREATED)


@bp.route('/api/experiments/<experiment_id>/tuner/<tpr_name>/stop', methods=['POST'])
def stop_tuner_job(experiment_id: str, tpr_name: str):
    """Stop tuner job."""
    exp = state.experiments.get(experiment_id)
    if not exp:
        return ApiResponse.error(f'Experiment {experiment_id} not found', HTTPStatus.NOT_FOUND)
    
    tuner = next((tj for tj in exp['tuner_jobs'] if tj['tpr_name'] == tpr_name), None)
    if not tuner:
        return ApiResponse.error(f"Tuner job for '{tpr_name}' not found.", HTTPStatus.NOT_FOUND)
    
    tuner['is_stopped'] = True
    
    # Convert all RUNNING trials to TERMINATED
    for trial in tuner['trials']:
        if trial['status'] == 'RUNNING':
            trial['status'] = 'TERMINATED'
            trial['performance'] = trial.get('performance') or round(random.uniform(40.0, 80.0), 3)
    
    return ApiResponse.success(status=HTTPStatus.NO_CONTENT)


@bp.route('/api/experiments/<experiment_id>/tuner/<tpr_name>', methods=['DELETE'])
def delete_tuner_job(experiment_id: str, tpr_name: str):
    """Delete tuner job."""
    exp = state.experiments.get(experiment_id)
    if not exp:
        return ApiResponse.error(f'Experiment {experiment_id} not found', HTTPStatus.NOT_FOUND)
    
    tuner = next((tj for tj in exp['tuner_jobs'] if tj['tpr_name'] == tpr_name), None)
    if not tuner:
        return ApiResponse.error(f"Tuner job for '{tpr_name}' not found.", HTTPStatus.NOT_FOUND)
    
    exp['tuner_jobs'].remove(tuner)
    return ApiResponse.success(status=HTTPStatus.NO_CONTENT)


# ----- GROMACS -----

@bp.route('/api/experiments/<experiment_id>/gmx', methods=['GET'])
def get_gmx_jobs(experiment_id: str):
    """List all GROMACS jobs for experiment."""
    exp = state.experiments.get(experiment_id)
    if not exp:
        return ApiResponse.error(f'Experiment {experiment_id} not found', HTTPStatus.NOT_FOUND)
    
    jobs = [state._clean_gromacs_job(gj) for gj in exp['gromacs_jobs']]
    return ApiResponse.success(jobs)


@bp.route('/api/experiments/<experiment_id>/gmx/<tpr_name>', methods=['GET'])
def get_gmx_job(experiment_id: str, tpr_name: str):
    """Get GROMACS job status."""
    exp = state.experiments.get(experiment_id)
    if not exp:
        return ApiResponse.error(f'Experiment {experiment_id} not found', HTTPStatus.NOT_FOUND)
    
    job = next((gj for gj in exp['gromacs_jobs'] if gj['tpr_name'] == tpr_name), None)
    if not job:
        return ApiResponse.error(f"GROMACS job for '{tpr_name}' not found.", HTTPStatus.NOT_FOUND)
    
    return ApiResponse.success(state._clean_gromacs_job(job))


@bp.route('/api/experiments/<experiment_id>/gmx/<tpr_name>', methods=['POST'])
def submit_gmx_job(experiment_id: str, tpr_name: str):
    """Submit GROMACS job."""
    exp = state.experiments.get(experiment_id)
    if not exp:
        return ApiResponse.error(f'Experiment {experiment_id} not found', HTTPStatus.NOT_FOUND)
    
    # Check if job already exists and return it
    existing = next((gj for gj in exp['gromacs_jobs'] if gj['tpr_name'] == tpr_name), None)
    if existing:
        return ApiResponse.success(state._clean_gromacs_job(existing), HTTPStatus.OK)
    
    # Get parameters from form
    np = int(request.form.get('np', 2))
    ntomp = int(request.form.get('ntomp', 8))
    nb = request.form.get('nb', 'cpu')
    pme = request.form.get('pme', 'cpu')
    extra_args = request.form.get('extra_args', '')
    
    # Create job
    job = state._create_gromacs_job(
        experiment_id, tpr_name,
        np=np, ntomp=ntomp, nb=nb, pme=pme,
        status='RUNNING', extra_args=extra_args
    )
    exp['gromacs_jobs'].append(job)
    
    return ApiResponse.success(state._clean_gromacs_job(job), HTTPStatus.CREATED)


@bp.route('/api/experiments/<experiment_id>/gmx/<tpr_name>', methods=['DELETE'])
def delete_gmx_job(experiment_id: str, tpr_name: str):
    """Delete GROMACS job."""
    exp = state.experiments.get(experiment_id)
    if not exp:
        return ApiResponse.error(f'Experiment {experiment_id} not found', HTTPStatus.NOT_FOUND)
    
    job = next((gj for gj in exp['gromacs_jobs'] if gj['tpr_name'] == tpr_name), None)
    if not job:
        return ApiResponse.error(f"GROMACS job for '{tpr_name}' not found.", HTTPStatus.NOT_FOUND)
    
    exp['gromacs_jobs'].remove(job)
    return ApiResponse.success(status=HTTPStatus.NO_CONTENT)


@bp.route('/api/experiments/<experiment_id>/gmx/<tpr_name>/log', methods=['GET'])
def get_gmx_job_log(experiment_id: str, tpr_name: str):
    """Get GROMACS job log."""
    exp = state.experiments.get(experiment_id)
    if not exp:
        return ApiResponse.error(f'Experiment {experiment_id} not found', HTTPStatus.NOT_FOUND)
    
    job = next((gj for gj in exp['gromacs_jobs'] if gj['tpr_name'] == tpr_name), None)
    if not job:
        return ApiResponse.error(f"GROMACS job for '{tpr_name}' not found.", HTTPStatus.NOT_FOUND)
    
    demo_log = """
      R E A L   C Y C L E   A N D   T I M E   A C C O U N T I N G

On 1 MPI rank

 Activity:              Num   Num      Call    Wall time         Giga-Cycles
                        Ranks Threads  Count      (s)         total sum    %
--------------------------------------------------------------------------------
 Domain decomp.            1    1       1000       1.989          5.345   0.4
 Neighbor search           1    1       1001      23.295         62.614   4.6
 Force                     1    1      50001     400.675       1076.964  78.7
 PME mesh                  1    1      50001      66.779        179.495  13.1
 NB X/F buffer ops.        1    1      99001       4.309         11.581   0.8
 Write traj.               1    1         11       0.026          0.071   0.0
 Update                    1    1      50001       3.775         10.148   0.7
 Constraints               1    1      50001       5.400         14.514   1.1
 Rest                                              2.702          7.263   0.5
--------------------------------------------------------------------------------
 Total                                           508.950       1367.994 100.0
--------------------------------------------------------------------------------

               Core t (s)   Wall t (s)        (%)
       Time:      508.950      508.950      100.0
                 (ns/day)    (hour/ns)
Performance:       16.976        1.414
Finished mdrun on rank 0 Sat Jul  5 16:26:40 2025
"""
    
    return ApiResponse.success(demo_log)


# ----- FILES -----

demo_files = [
    {'name': 'SPC.tpr', 'url': '/api/experiments/aaaaa/files/md.tpr', 'size': 514912},
    {'name': 'ABC.tpr', 'url': '/api/experiments/aaaaa/files/md.tpr', 'size': 514912},
    {'name': 'md.tpr', 'url': '/api/experiments/aaaaa/files/md.tpr', 'size': 321654},
    {'name': 'trajectory.xtc', 'url': '/api/experiments/aaaaa/files/trajectory.xtc', 'size': 3038996},
    {'name': 'structure.pdb', 'url': '/api/experiments/aaaaa/files/structure.pdb', 'size': 630792},
    {'name': 'structure.gro', 'url': '/api/experiments/aaaaa/files/structure.gro', 'size': 321654},
]


@bp.route('/api/experiments/<experiment_id>/files', methods=['GET'])
def list_experiment_files(experiment_id: str):
    """List files for experiment."""
    ext_param = request.args.get('ext', '').lower()
    extensions = [ext.strip() for ext in ext_param.split(',') if ext.strip()]
    
    if extensions:
        files = []
        for f in demo_files:
            name = str(f['name'])
            if '.' in name:
                file_ext = name.split('.')[-1]
                if file_ext in extensions:
                    files.append(f)
    else:
        files = demo_files
    
    # Update has_tpr_files flag if TPR files exist
    exp = state.experiments.get(experiment_id)
    if exp and any(str(f['name']).endswith('.tpr') for f in demo_files):
        exp['has_tpr_files'] = True
    
    return ApiResponse.success(files)


@bp.route('/api/experiments/<experiment_id>/files/<path:path>', methods=['GET'])
def get_experiment_file(experiment_id: str, path: str):
    """Get experiment file."""
    file_path = Path(__file__).parent / "data" / path
    if file_path.exists():
        return send_file(file_path, as_attachment=False)
    else:
        return ApiResponse.error('File not found', HTTPStatus.NOT_FOUND)
