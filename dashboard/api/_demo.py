"""
This is just the demo version of the API. It just returns hardcoded responses.

I mainly use it to develop the frontend.
"""

from flask import Flask, Blueprint, request, send_file
from flask_cors import CORS
from uuid import uuid4
from api_response import ApiResponse


bp = Blueprint('dash', __name__)
CORS(bp)


gromacs_demo_job = {
    'id': 1,
    'experiment_id': 'abcde',
    'created_at': '2025-01-15T10:30:00',
    'tpr_name': 'LSD.tpr',
    'job_name': 'gromacs-6bec87ce-6f0c-4f8c-9572-426a1c62f44d',
    'pme': 'cpu',
    'nb': 'cpu',
    'np': 2,
    'ntomp': 8,
    'extra_args': '',
    'start_timestamp': 1754047422,
    'nsteps': 100000,
    'performance': None,
    'status': 'RUNNING',
    'nsteps_done': 76543,
    'estimated_time': 408
}


gromacs_demo_jobs = [gromacs_demo_job, {
    'id': 2,
    'experiment_id': 'abcde',
    'created_at': '2025-01-15T10:00:00',
    'tpr_name': 'MDMA.tpr',
    'job_name': 'gromacs-6bec87ce-6f0c-4f8c-9572-426a1c62f44d',
    'pme': 'cpu',
    'nb': 'gpu',
    'np': 8,
    'ntomp': 1,
    'extra_args': '-v  -nt 8 -ddorder pp_pme',
    'start_timestamp': 1754047422,
    'nsteps': 100000,
    'performance': 70.158,
    'status': 'TERMINATED',
    'nsteps_done': 100000,
    'estimated_time': 0
}]


tuner_demo_status = {
    'id': 1,
    'tuner_run_id': '6bec87ce-6f0c-4f8c-9572-426a1c62f44d',
    'experiment_id': 'abcde',
    'tpr_name': 'LSD.tpr',
    'is_pending': False,
    'error_message': None,
    'created_at': '2025-01-15T09:30:00',
    'is_stopped': False,
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

tuner_demo_statuses = [
    {
        'id': 1,
        'tuner_run_id': '6bec87ce-6f0c-4f8c-9572-426a1c62f44d',
        'experiment_id': 'bbbbb',
        'tpr_name': 'LSD.tpr',
        'is_pending': False,
        'error_message': None,
        'created_at': '2025-01-15T09:30:00',
        'is_stopped': False,
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
    },
    {
        'id': 2,
        'tuner_run_id': '7bec87ce-6f0c-4f8c-9572-426a1c62f44e',
        'experiment_id': 'bbbbb',
        'tpr_name': 'MDMA.tpr',
        'is_pending': False,
        'error_message': None,
        'created_at': '2025-01-15T09:45:00',
        'is_stopped': True,
        'summary': {
            'RUNNING': 1,
            'PENDING': 1,
            'TERMINATED': 2,
            'ERROR': 0
        },
        'trials': [
            {
                'id': 'e5168_00000',
                'status': 'TERMINATED',
                'np': 4,
                'ntomp': 2,
                'nb': 'gpu',
                'pme': 'cpu',
                'performance': 65.234
            },
            {
                'id': 'e5168_00001',
                'status': 'TERMINATED',
                'np': 8,
                'ntomp': 1,
                'nb': 'gpu',
                'pme': 'gpu',
                'performance': None
            }
        ],
        'cluster_resources': '0/32 CPUs, 0/1 GPUs used'
    },
    {
        'id': 3,
        'tuner_run_id': None,
        'experiment_id': 'bbbbb',
        'tpr_name': 'Pending.tpr',
        'is_pending': True,
        'error_message': None,
        'created_at': '2025-01-15T10:00:00',
        'is_stopped': False,
        'summary': {
            'PENDING': 1
        },
        'trials': [],
        'cluster_resources': 'Pending'
    },
    {
        'id': 4,
        'tuner_run_id': None,
        'experiment_id': 'bbbbb',
        'tpr_name': 'Failed.tpr',
        'is_pending': False,
        'error_message': 'TPR modification failed: Job tpr-mod-abcde-1234567890 failed',
        'created_at': '2025-01-15T10:15:00',
        'is_stopped': False,
        'summary': {
            'ERROR': 1
        },
        'trials': [],
        'cluster_resources': 'Error'
    }
]


demo_experiments = [
    {
        'id': 'aaaaa',
        'created_at': '2025-01-15T08:00:00',
        'updated_at': '2025-01-15T08:00:00',
        'name': 'Cancer cure',
        'source_message': "Created by uploading TPR file 'cancer_cure.tpr'.",
        'mdrepo_id': None,
        'step': 0,
        'status': 'setup',
        'notebook': {
            'id': 1,
            'experiment_id': 'aaaaa',
            'token': '2f2be97e-15db-4cb4-8ef7-905efe5a4968',
            'status': 'UNKNOWN',
            'path': '/__BASE_PATH__/notebook/aaaaa/?token=2f2be97e-15db-4cb4-8ef7-905efe5a4968'
        },
        'tuner_jobs': [],
        'gromacs_jobs': [],
    },
    {
        'id': 'bbbbb',
        'created_at': '2025-01-15T09:00:00',
        'updated_at': '2025-01-15T10:30:00',
        'name': 'HIV protein behavior research for drug development',
        'source_message': "Created by downloading repository from 'https://zenodo.org/records/7261108'.",
        'mdrepo_id': None,
        'step': 2,
        'status': 'simulating',
        'notebook': {
            'id': 2,
            'experiment_id': 'bbbbb',
            'token': '191eb452-5505-4328-9004-99eb1b0d570a',
            'status': 'RUNNING',
            'path': '/__BASE_PATH__/notebook/bbbbb/?token=191eb452-5505-4328-9004-99eb1b0d570a'
        },
        'tuner_jobs': tuner_demo_statuses,
        'gromacs_jobs': gromacs_demo_jobs,
    },
    {
        'id': 'ccccc',
        'created_at': '2025-01-15T07:00:00',
        'updated_at': '2025-01-15T12:00:00',
        'name': 'My first experiment',
        'source_message': "Created by uploading TPR file 'my_first_experiment.tpr'.",
        'mdrepo_id': 'xej9e-x3720',
        'step': 5,
        'status': 'published',
        'notebook': {
            'id': 3,
            'experiment_id': 'ccccc',
            'token': '2578b922-7b12-49d0-8962-b2d79afda1dc',
            'status': 'DOWN',
            'path': '/__BASE_PATH__/notebook/ccccc/?token=2578b922-7b12-49d0-8962-b2d79afda1dc'
        },
        'tuner_jobs': [],
        'gromacs_jobs': gromacs_demo_jobs,
    },
]


# ----- HEALTH CHECK -----

@bp.route('/api/metrics', methods=['GET'])
def get_metrics():
    return ApiResponse.success({'cpu': 17.8, 'memory': 64, 'gpu': 4})


# ----- EXPERIMENTS -----

@bp.route('/api/experiments', methods=['GET'])
def list_experiments():
    return ApiResponse.success(demo_experiments)


@bp.route('/api/experiments/<experiment_id>', methods=['GET'])
def get_experiment(experiment_id):
    return ApiResponse.success(next(e for e in demo_experiments if e['id'] == experiment_id))


@bp.route('/api/experiments', methods=['POST'])
def create_experiment():
    return ApiResponse.success(demo_experiments[0])


@bp.route('/api/experiments/<experiment_id>', methods=['DELETE'])
def delete_experiment(experiment_id):
    return ApiResponse.success()

@bp.route('/api/experiments/<experiment_id>/step', methods=['GET'])
def get_experiment_step(experiment_id):
    experiment = next(e for e in demo_experiments if e['id'] == experiment_id)
    return ApiResponse.success(experiment['step'])

# ----- NOTEBOOK -----

notebook_running = False

@bp.route('/api/experiments/<experiment_id>/notebook', methods=['POST'])
def create_notebook(experiment_id):
    global notebook_running
    notebook_running = True
    experiment = next(e for e in demo_experiments if e['id'] == experiment_id)
    experiment['notebook']['status'] = 'RUNNING'
    return ApiResponse.success(experiment['notebook'])


@bp.route('/api/experiments/<experiment_id>/notebook', methods=['DELETE'])
def delete_notebook(experiment_id):
    global notebook_running
    notebook_running = False
    experiment = next(e for e in demo_experiments if e['id'] == experiment_id)
    experiment['notebook']['status'] = 'DOWN'
    return ApiResponse.success()


@bp.route('/api/experiments/<experiment_id>/notebook', methods=['GET'])
def get_notebook(experiment_id):
    experiment = next(e for e in demo_experiments if e['id'] == experiment_id)
    return ApiResponse.success(experiment['notebook'])


# ----- TUNER -----

@bp.route('/api/experiments/<experiment_id>/tuner/<tpr_name>', methods=['POST'])
def submit_tuner(experiment_id, tpr_name):
    new_tuner = tuner_demo_status.copy()
    new_tuner['id'] = max([t['id'] for t in tuner_demo_statuses]) + 1 if tuner_demo_statuses else 1
    new_tuner['tuner_run_id'] = str(uuid4())
    new_tuner['experiment_id'] = experiment_id
    new_tuner['tpr_name'] = tpr_name
    new_tuner['is_pending'] = False
    new_tuner['error_message'] = None
    new_tuner['created_at'] = '2025-01-15T12:00:00'
    tuner_demo_statuses.append(new_tuner)
    return ApiResponse.success(new_tuner)


@bp.route('/api/experiments/<experiment_id>/tuner', methods=['GET'])
def get_tuner_statuses(experiment_id):
    experiment_tuners = [t for t in tuner_demo_statuses if t['experiment_id'] == experiment_id]
    return ApiResponse.success(experiment_tuners)


@bp.route('/api/experiments/<experiment_id>/tuner/<tpr_name>', methods=['GET'])
def get_tuner_status(experiment_id, tpr_name):
    tuner = next((t for t in tuner_demo_statuses if t['experiment_id'] == experiment_id and t['tpr_name'] == tpr_name), None)
    if tuner:
        return ApiResponse.success(tuner)
    else:
        return ApiResponse.error(f"Tuner for '{tpr_name}' not found.")


@bp.route('/api/experiments/<experiment_id>/tuner/<tpr_name>/stop', methods=['POST'])
def stop_tuner(experiment_id, tpr_name):
    tuner = next((t for t in tuner_demo_statuses if t['experiment_id'] == experiment_id and t['tpr_name'] == tpr_name), None)
    if tuner:
        # Convert RUNNING trials to TERMINATED
        for trial in tuner['trials']:
            if trial['status'] == 'RUNNING':
                trial['status'] = 'TERMINATED'

        # Update summary
        if 'RUNNING' in tuner['summary']:
            terminated_count = tuner['summary'].get('TERMINATED', 0) + tuner['summary'].get('RUNNING', 0)
            tuner['summary']['TERMINATED'] = terminated_count
            tuner['summary']['RUNNING'] = 0

        tuner['is_stopped'] = True

        return ApiResponse.success()
    else:
        return ApiResponse.error('Tuner not found.')


@bp.route('/api/experiments/<experiment_id>/tuner/<tpr_name>', methods=['DELETE'])
def delete_tuner(experiment_id, tpr_name):
    tuner = next((t for t in tuner_demo_statuses if t['experiment_id'] == experiment_id and t['tpr_name'] == tpr_name), None)
    if tuner:
        tuner_demo_statuses.remove(tuner)
        return ApiResponse.success()
    else:
        return ApiResponse.error('Tuner not found.')


# ----- GROMACS -----

@bp.route('/api/experiments/<experiment_id>/gmx/<tpr_name>', methods=['POST'])
def submit_gmx(experiment_id, tpr_name):
    existing_job = next((j for j in gromacs_demo_jobs if j['experiment_id'] == experiment_id and j['tpr_name'] == tpr_name), None)
    if existing_job:
        return ApiResponse.error(f"Gromacs job for '{tpr_name}' already exists.")

    job = gromacs_demo_job.copy()
    job['id'] = max([j['id'] for j in gromacs_demo_jobs]) + 1 if gromacs_demo_jobs else 1
    job['experiment_id'] = experiment_id
    job['tpr_name'] = tpr_name
    job['np'] = int(request.form['np'])
    job['ntomp'] = int(request.form['ntomp'])
    job['nb'] = request.form['nb']
    job['pme'] = request.form['pme']
    job['extra_args'] = request.form['extra_args']
    job['created_at'] = '2025-01-15T12:00:00'
    job['job_name'] = f'gromacs-{uuid4()}'

    gromacs_demo_jobs.append(job)
    return ApiResponse.success(job)


@bp.route('/api/experiments/<experiment_id>/gmx', methods=['GET'])
def get_gmx_statuses(experiment_id):
    experiment_jobs = [j for j in gromacs_demo_jobs if j['experiment_id'] == experiment_id]
    return ApiResponse.success(experiment_jobs)


@bp.route('/api/experiments/<experiment_id>/gmx/<tpr_name>', methods=['GET'])
def get_gmx_status(experiment_id, tpr_name):
    job = next((j for j in gromacs_demo_jobs if j['experiment_id'] == experiment_id and j['tpr_name'] == tpr_name), None)
    if job:
        return ApiResponse.success(job)
    else:
        return ApiResponse.error(f"Gromacs job for '{tpr_name}' not found.")


@bp.route('/api/experiments/<experiment_id>/gmx/<tpr_name>', methods=['DELETE'])
def delete_gmx(experiment_id, tpr_name):
    job = next((j for j in gromacs_demo_jobs if j['experiment_id'] == experiment_id and j['tpr_name'] == tpr_name), None)
    if job:
        gromacs_demo_jobs.remove(job)
        return ApiResponse.success()
    else:
        return ApiResponse.error('Gromacs job not found.')


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
 Breakdown of PME mesh activities
--------------------------------------------------------------------------------
 PME spread                1    1      50001      29.078         78.158   5.7
 PME gather                1    1      50001      17.936         48.210   3.5
 PME 3D-FFT                1    1     100002      16.920         45.479   3.3
 PME solve Elec            1    1      50001       2.442          6.563   0.5
--------------------------------------------------------------------------------

               Core t (s)   Wall t (s)        (%)
       Time:      508.950      508.950      100.0
                 (ns/day)    (hour/ns)
Performance:       16.976        1.414
Finished mdrun on rank 0 Sat Jul  5 16:26:40 2025
"""

@bp.route('/api/experiments/<experiment_id>/gmx/<tpr_name>/log', methods=['GET'])
def get_gmx_log(experiment_id, tpr_name):
    return ApiResponse.success(demo_log)


# ----- PUBLISHING -----

demo_experiment = {"id": "xej9e-x3720", "created": "2025-05-11T14:24:31.964333+00:00", "updated": "2025-05-11T14:24:32.188250+00:00", "links": {"applicable-requests": "https://mdrepo.eu/api/experiments/xej9e-x3720/draft/requests/applicable", "communities": {"b53d8a89-d370-475c-be34-67b698e088b1": {"self": "https://mdrepo.eu/api/communities/b53d8a89-d370-475c-be34-67b698e088b1", "self_html": "https://mdrepo.eu/communities/ceitec/records"}}, "draft": "https://mdrepo.eu/api/experiments/xej9e-x3720/draft", "edit_html": "https://mdrepo.eu/experiments/xej9e-x3720/edit", "files": "https://mdrepo.eu/api/experiments/xej9e-x3720/draft/files", "latest": "https://mdrepo.eu/api/experiments/xej9e-x3720/versions/latest", "latest_html": "https://mdrepo.eu/experiments/xej9e-x3720/latest", "publish": "https://mdrepo.eu/api/experiments/xej9e-x3720/draft/actions/publish", "requests": "https://mdrepo.eu/api/experiments/xej9e-x3720/draft/requests", "self": "https://mdrepo.eu/api/experiments/xej9e-x3720/draft", "self_html": "https://mdrepo.eu/experiments/xej9e-x3720/preview", "versions": "https://mdrepo.eu/api/experiments/xej9e-x3720/versions"}, "revision_id": 3, "$schema": "local://experiments-1.0.0.json", "metadata": {"simulations": [{"_dump_sw_version": "127", "_exit_code": 0, "_gromacs_version": "5.1.4", "_metadata_date": "2024-10-24T08:25:13.824043", "_metadump_version": "1.0.0", "_protein_sequences": ["LRIPCCPVNLKRLLVVVVVVVLVVVVIVGALLMGL", "LRIPCCPVNLKRLLVVVVVVVLVVVVIVGALLMGL"], "_tpx_version": "103", "_uniprot_id": "P15785", "detailed_information": {"comm_mode": "linear", "constraint_algorithm": "lincs", "electrostatic_interactions": {"coulomb_modifier": "potential-shift", "coulombtype": "pme", "epsilon_r": 1.0, "epsilon_rf": -1.0, "rcoulomb": 1.2}, "fourierspacing": 0.12, "lincs_iter": 1, "lincs_order": 4, "neighbour_list": {"cutoff_scheme": "verlet", "nstlist": 20, "pbc": "xyz", "rlist": 1.2}, "nstcomm": 1000, "thermostat": {"nsttcouple": 20, "tau_t": [1.0, 1.0, 1.0], "tc_grps": {
    "name": "protein_cysp lipids water_and_ions", "nr": 3}, "tcoupl": "nose-hoover"}, "van_der_Waals_interactions": {"dispcorr": "enerpres", "rvdw": 1.2, "rvdw_switch": 1.0, "vdw_modifier": "force-switch", "vdw_type": "cut-off"}}, "file_identification": {"authors": ["6969-6969-6969-6969"], "description": "Test file.", "doi": "69", "name": "SPC.tpr", "simulation_year": "1984"}, "main_information": {"AWH_adaptive_biasing": False, "force_field": "probably has to be set by the user", "free_energy_calculation": "no", "molecules": [{"id": "molecule 1", "count": 2, "name": "spc", "residues": ["L", "R", "I", "P", "cysp", "cysp", "P", "V", "N", "L", "K", "R", "L", "L", "V", "V", "V", "V", "V", "V", "V", "L", "V", "V", "V", "V", "I", "V", "G", "A", "L", "L", "M", "G", "L"]}, {"id": "molecule 2", "count": 101, "name": "dppc", "residues": ["dppc"]}, {"id": "molecule 3", "count": 34, "name": "popc", "residues": ["popc"]}, {"id": "molecule 4", "count": 17, "name": "chl1", "residues": ["chl1"]}, {"id": "molecule 5", "count": 17, "name": "popg", "residues": ["popg"]}, {"id": "molecule 6", "count": 101, "name": "dppc", "residues": ["dppc"]}, {"id": "molecule 7", "count": 34, "name": "popc", "residues": ["popc"]}, {"id": "molecule 8", "count": 17, "name": "chl1", "residues": ["chl1"]}, {"id": "molecule 9", "count": 17, "name": "popg", "residues": ["popg"]}, {"id": "molecule 10", "count": 27040, "name": "sol", "residues": ["sol"]}, {"id": "molecule 11", "count": 67, "name": "na", "residues": ["na"]}, {"id": "molecule 12", "count": 39, "name": "cl", "residues": ["cl"]}], "reference_temperature": [310.0, 310.0, 310.0], "simulation_length": 100000.0, "simulation_time_step": 0.002, "simulation_type": "molecular dynamics", "statistical_ensamble": "NVT (canonical)", "umbrella_sampling": False}}]}, "state": "draft", "state_timestamp": "2025-05-11T14:24:32.008171+00:00", "parent": {"id": "kvq2y-02940", "workflow": "default", "communities": {"ids": ["b53d8a89-d370-475c-be34-67b698e088b1"], "default": "b53d8a89-d370-475c-be34-67b698e088b1"}}, "files": {"enabled": True}}


@bp.route('/api/experiments/<experiment_id>/publish', methods=['POST'])
def publish_experiment(experiment_id):
    return ApiResponse.success(demo_experiment)


# ----- FILES -----

demo_files = [
    {'name': 'SPC.tpr', 'url': 'http://localhost:8888/api/experiments/aaaaa/files/md.tpr', 'size': 514912},
    {'name': 'ABC.tpr', 'url': 'http://localhost:8888/api/experiments/aaaaa/files/md.tpr', 'size': 514912},
    {'name': 'trajectory.xtc', 'url': 'http://localhost:8888/api/experiments/aaaaa/files/sampled.xtc', 'size': 3038996},
    {'name': 'structure.pdb', 'url': 'http://localhost:8888/api/experiments/aaaaa/files/minimal.pdb', 'size': 630792},
    {'name': 'structure.gro', 'url': '/api/experiments/aaaaa/files/structure.gro', 'size': 321654},
]


@bp.route('/api/experiments/<experiment_id>/files', methods=['GET'])
def list_experiment_files(experiment_id):
    ext_param = request.args.get('ext', '').lower()
    extensions = [ext.strip() for ext in ext_param.split(',') if ext.strip()]
    files = list(filter(lambda f: f['name'].split('.').pop() in extensions, demo_files))
    return ApiResponse.success(files)


@bp.route('/api/experiments/<experiment_id>/files/<path:path>', methods=['GET'])
def get_experiment_file(experiment_id, path: str):
    from pathlib import Path
    file_path = Path(__file__).parent / "_demo" / path
    return send_file(file_path, as_attachment=False)


if __name__ == '__main__':
    app = Flask(__name__)
    app.register_blueprint(bp)
    app.run(debug=True, host='0.0.0.0', port=8888)
