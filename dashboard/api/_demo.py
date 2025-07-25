"""
This is just the demo version of the API. It just returns hardcoded responses.

I mainly use it to develop the frontend.
"""

from flask import Flask, Blueprint, request, send_file
from flask_cors import CORS
from api_response import ApiResponse


bp = Blueprint('dash', __name__)
CORS(bp)


gromacs_demo_job = {
    'experiment_id': 'abcde',
    'tpr_name': 'LSD.tpr',
    'np': 2,
    'ntomp': 8,
    'pme': 'cpu',
    'nb': 'cpu',
    'extra_args': '',
    'job_name': 'gromacs-6bec87ce-6f0c-4f8c-9572-426a1c62f44d',
    'status': 'RUNNING',
    'nsteps': 100000,
    'nsteps_done': 76543,
    'performance': None
}

gromacs_demo_jobs = {
    'LSD.tpr': gromacs_demo_job,
    'MDMA.tpr': {
        'experiment_id': 'abcde',
        'tpr_name': 'MDMA.tpr',
        'np': 8,
        'ntomp': 1,
        'nb': 'gpu',
        'pme': 'cpu',
        'extra_args': '-v  -nt 8 -ddorder pp_pme',
        'job_name': 'gromacs-6bec87ce-6f0c-4f8c-9572-426a1c62f44d',
        'status': 'TERMINATED',
        'nsteps': 100000,
        'nsteps_done': 100000,
        'performance': 70.158
    }
}


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

tuner_demo_statuses = {
    "LSD.tpr": tuner_demo_status,
    "MDMA.tpr": tuner_demo_status,
}


demo_experiments = [
    {
        'id': 'aaaaa',
        'name': 'Cancer cure',
        'source_message': "Created by uploading TPR file 'cancer_cure.tpr''.",
        'step': 0,
        'status': 'setup',
        'notebook_status': 'UNKNOWN',
        'token': '2f2be97e-15db-4cb4-8ef7-905efe5a4968',
        'tuner_jobs': {},
        'gromacs_jobs': {},
    },
    {
        'id': 'bbbbb',
        'name': 'HIV protein behavior research for drug development',
        'source_message': "Created by downloading repository from 'https://zenodo.org/records/7261108'.",
        'step': 3,
        'status': 'simulating',
        'notebook_status': 'RUNNING',
        'token': '191eb452-5505-4328-9004-99eb1b0d570a',
        'tuner_jobs': tuner_demo_statuses,
        'gromacs_jobs': gromacs_demo_jobs,
    },
    {
        'id': 'ccccc',
        'name': 'My first experiment',
        'source_message': "Created by uploading TPR file 'my_first_experiment.tpr'.",
        'step': 5,
        'status': 'published',
        'notebook_status': 'DOWN',
        'token': '2578b922-7b12-49d0-8962-b2d79afda1dc',
        'tuner_jobs': {},
        'gromacs_jobs': gromacs_demo_jobs,
    },
]


# ----- HEALTH CHECK -----

@bp.route('/api/metrics', methods=['GET'])
def get_metrics():
    return ApiResponse.success({'cpu': 20, 'memory': 64, 'gpu': 4})


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


# ----- NOTEBOOK -----

notebook_running = False

@bp.route('/api/experiments/<experiment_id>/notebook', methods=['POST'])
def create_notebook(experiment_id):
    global notebook_running
    notebook_running = True
    return ApiResponse.success({
        'status': 'PENDING',
        'path': '/__BASE_PATH__/notebook/' + experiment_id
    })


@bp.route('/api/experiments/<experiment_id>/notebook', methods=['DELETE'])
def delete_notebook(experiment_id):
    global notebook_running
    notebook_running = False
    return ApiResponse.success()


@bp.route('/api/experiments/<experiment_id>/notebook', methods=['GET'])
def get_notebook(experiment_id):
    return ApiResponse.success({
        'status': 'RUNNING' if notebook_running else 'DOWN',
        'path': '/__BASE_PATH__/notebook/' + experiment_id
    })


# ----- TUNER -----

@bp.route('/api/experiments/<experiment_id>/tuner/<tpr_name>', methods=['POST'])
def submit_tuner(experiment_id, tpr_name):
    tuner_demo_statuses[tpr_name] = tuner_demo_status
    return ApiResponse.success(tuner_demo_status)


@bp.route('/api/experiments/<experiment_id>/tuner', methods=['GET'])
def get_tuner_statuses(experiment_id):
    return ApiResponse.success(tuner_demo_statuses)


@bp.route('/api/experiments/<experiment_id>/tuner/<tpr_name>', methods=['GET'])
def get_tuner_status(experiment_id, tpr_name):
    if tpr_name in tuner_demo_statuses:
        return ApiResponse.success(tuner_demo_statuses[tpr_name])
    else:
        return ApiResponse.error(f"Tuner for '{tpr_name}' not found.")


@bp.route('/api/experiments/<experiment_id>/tuner/<tpr_name>', methods=['DELETE'])
def delete_tuner(experiment_id, tpr_name):
    if tuner_demo_statuses.pop(tpr_name, None) is not None:
        return ApiResponse.success()
    else:
        return ApiResponse.error('Tuner not found.')


# ----- GROMACS -----

@bp.route('/api/experiments/<experiment_id>/gmx/<tpr_name>', methods=['POST'])
def submit_gmx(experiment_id, tpr_name):
    if tpr_name in gromacs_demo_jobs:
        return ApiResponse.error(f"Gromacs job for '{tpr_name}' already exists.")

    job = gromacs_demo_job.copy()
    job['np'] = request.form['np']
    job['ntomp'] = request.form['ntomp']
    job['nb'] = request.form['nb']
    job['pme'] = request.form['pme']
    job['extra_args'] = request.form['extra_args']

    gromacs_demo_jobs[tpr_name] = job
    return ApiResponse.success(job)


@bp.route('/api/experiments/<experiment_id>/gmx', methods=['GET'])
def get_gmx_statuses(experiment_id):
    return ApiResponse.success(gromacs_demo_jobs)


@bp.route('/api/experiments/<experiment_id>/gmx/<tpr_name>', methods=['GET'])
def get_gmx_status(experiment_id, tpr_name):
    if tpr_name in gromacs_demo_jobs:
        return ApiResponse.success(gromacs_demo_jobs[tpr_name])
    else:
        return ApiResponse.error(f"Gromacs job for '{tpr_name}' not found.")


@bp.route('/api/experiments/<experiment_id>/gmx/<tpr_name>', methods=['DELETE'])
def delete_gmx(experiment_id, tpr_name):
    if gromacs_demo_jobs.pop(tpr_name, None) is not None:
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


@bp.route('/api/experiments/<experiment_id>/publish', methods=['GET'])
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
