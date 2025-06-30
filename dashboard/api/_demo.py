"""
This is just the demo version of the API. It just returns hardcoded responses.

I mainly use it to develop the frontend.
"""

from flask import Flask, Blueprint, request, send_file
from flask_cors import CORS
from api_response import ApiResponse


bp = Blueprint('dash', __name__)
CORS(bp)


# ----- HEALTH CHECK -----

@bp.route('/api/metrics', methods=['GET'])
def get_metrics():
    return ApiResponse.success({'cpu': 20, 'memory': 64, 'gpu': 4})


# ----- EXPERIMENTS -----

demo_experiments = [
    {
        'id': 'aaaaa',
        'name': 'Cancer cure',
        'source_message': "Created by uploading TPR file 'cancer_cure.tpr''.",
        'step': 0,
        'status': 'setup',
        'token': '2f2be97e-15db-4cb4-8ef7-905efe5a4968',
    },
    {
        'id': 'bbbbb',
        'name': 'HIV protein behavior research for drug development',
        'source_message': "Created by downloading repository from 'https://zenodo.org/records/7261108'.",
        'step': 3,
        'status': 'simulating',
        'token': '191eb452-5505-4328-9004-99eb1b0d570a',
    },
    {
        'id': 'ccccc',
        'name': 'My first experiment',
        'source_message': "Created by uploading TPR file 'my_first_experiment.tpr'.",
        'step': 5,
        'status': 'published',
        'token': '2578b922-7b12-49d0-8962-b2d79afda1dc',
    },
]


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
    return ApiResponse.success()


@bp.route('/api/experiments/<experiment_id>/notebook', methods=['DELETE'])
def delete_notebook(experiment_id):
    global notebook_running
    notebook_running = False
    return ApiResponse.success()


@bp.route('/api/experiments/<experiment_id>/notebook', methods=['GET'])
def get_notebook(experiment_id):
    return ApiResponse.success({'up': notebook_running, 'path': '/__BASE_PATH__/notebook/' + experiment_id})


# ----- TUNER -----

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

gromacs_demo_job = {
    'id': 'e5167_00001',
    'status': 'RUNNING',
    'np': 2,
    'ntomp': 8,
    'nb': 'cpu',
    'pme': 'cpu',
    'performance': None
}

gromacs_demo_jobs = {
    'LSD.tpr': gromacs_demo_job,
    'MDMA.tpr': {
        'id': 'e5167_00002',
        'status': 'TERMINATED',
        'np': 8,
        'ntomp': 1,
        'nb': 'gpu',
        'pme': 'cpu',
        'performance': 70.158
    }
}

@bp.route('/api/experiments/<experiment_id>/gmx/<tpr_name>', methods=['POST'])
def submit_gmx(experiment_id, tpr_name):
    if tpr_name in gromacs_demo_jobs:
        return ApiResponse.error(f"Gromacs job for '{tpr_name}' already exists.")

    job = gromacs_demo_job.copy()
    job['np'] = request.form.get('np', job['np'])
    job['ntomp'] = request.form.get('ntomp', job['ntomp'])
    job['nb'] = request.form.get('nb', job['nb'])
    job['pme'] = request.form.get('pme', job['pme'])
    
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


# ----- PUBLISHING -----

demo_experiment = {"id": "xej9e-x3720", "created": "2025-05-11T14:24:31.964333+00:00", "updated": "2025-05-11T14:24:32.188250+00:00", "links": {"applicable-requests": "https://mdrepo.eu/api/experiments/xej9e-x3720/draft/requests/applicable", "communities": {"b53d8a89-d370-475c-be34-67b698e088b1": {"self": "https://mdrepo.eu/api/communities/b53d8a89-d370-475c-be34-67b698e088b1", "self_html": "https://mdrepo.eu/communities/ceitec/records"}}, "draft": "https://mdrepo.eu/api/experiments/xej9e-x3720/draft", "edit_html": "https://mdrepo.eu/experiments/xej9e-x3720/edit", "files": "https://mdrepo.eu/api/experiments/xej9e-x3720/draft/files", "latest": "https://mdrepo.eu/api/experiments/xej9e-x3720/versions/latest", "latest_html": "https://mdrepo.eu/experiments/xej9e-x3720/latest", "publish": "https://mdrepo.eu/api/experiments/xej9e-x3720/draft/actions/publish", "requests": "https://mdrepo.eu/api/experiments/xej9e-x3720/draft/requests", "self": "https://mdrepo.eu/api/experiments/xej9e-x3720/draft", "self_html": "https://mdrepo.eu/experiments/xej9e-x3720/preview", "versions": "https://mdrepo.eu/api/experiments/xej9e-x3720/versions"}, "revision_id": 3, "$schema": "local://experiments-1.0.0.json", "metadata": {"simulations": [{"_dump_sw_version": "127", "_exit_code": 0, "_gromacs_version": "5.1.4", "_metadata_date": "2024-10-24T08:25:13.824043", "_metadump_version": "1.0.0", "_protein_sequences": ["LRIPCCPVNLKRLLVVVVVVVLVVVVIVGALLMGL", "LRIPCCPVNLKRLLVVVVVVVLVVVVIVGALLMGL"], "_tpx_version": "103", "_uniprot_id": "P15785", "detailed_information": {"comm_mode": "linear", "constraint_algorithm": "lincs", "electrostatic_interactions": {"coulomb_modifier": "potential-shift", "coulombtype": "pme", "epsilon_r": 1.0, "epsilon_rf": -1.0, "rcoulomb": 1.2}, "fourierspacing": 0.12, "lincs_iter": 1, "lincs_order": 4, "neighbour_list": {"cutoff_scheme": "verlet", "nstlist": 20, "pbc": "xyz", "rlist": 1.2}, "nstcomm": 1000, "thermostat": {"nsttcouple": 20, "tau_t": [1.0, 1.0, 1.0], "tc_grps": {
    "name": "protein_cysp lipids water_and_ions", "nr": 3}, "tcoupl": "nose-hoover"}, "van_der_Waals_interactions": {"dispcorr": "enerpres", "rvdw": 1.2, "rvdw_switch": 1.0, "vdw_modifier": "force-switch", "vdw_type": "cut-off"}}, "file_identification": {"authors": ["6969-6969-6969-6969"], "description": "Test file.", "doi": "69", "name": "SPC.tpr", "simulation_year": "1984"}, "main_information": {"AWH_adaptive_biasing": False, "force_field": "probably has to be set by the user", "free_energy_calculation": "no", "molecules": [{"id": "molecule 1", "count": 2, "name": "spc", "residues": ["L", "R", "I", "P", "cysp", "cysp", "P", "V", "N", "L", "K", "R", "L", "L", "V", "V", "V", "V", "V", "V", "V", "L", "V", "V", "V", "V", "I", "V", "G", "A", "L", "L", "M", "G", "L"]}, {"id": "molecule 2", "count": 101, "name": "dppc", "residues": ["dppc"]}, {"id": "molecule 3", "count": 34, "name": "popc", "residues": ["popc"]}, {"id": "molecule 4", "count": 17, "name": "chl1", "residues": ["chl1"]}, {"id": "molecule 5", "count": 17, "name": "popg", "residues": ["popg"]}, {"id": "molecule 6", "count": 101, "name": "dppc", "residues": ["dppc"]}, {"id": "molecule 7", "count": 34, "name": "popc", "residues": ["popc"]}, {"id": "molecule 8", "count": 17, "name": "chl1", "residues": ["chl1"]}, {"id": "molecule 9", "count": 17, "name": "popg", "residues": ["popg"]}, {"id": "molecule 10", "count": 27040, "name": "sol", "residues": ["sol"]}, {"id": "molecule 11", "count": 67, "name": "na", "residues": ["na"]}, {"id": "molecule 12", "count": 39, "name": "cl", "residues": ["cl"]}], "reference_temperature": [310.0, 310.0, 310.0], "simulation_length": 100000.0, "simulation_time_step": 0.002, "simulation_type": "molecular dynamics", "statistical_ensamble": "NVT (canonical)", "umbrella_sampling": False}}]}, "state": "draft", "state_timestamp": "2025-05-11T14:24:32.008171+00:00", "parent": {"id": "kvq2y-02940", "workflow": "default", "communities": {"ids": ["b53d8a89-d370-475c-be34-67b698e088b1"], "default": "b53d8a89-d370-475c-be34-67b698e088b1"}}, "files": {"enabled": True}}


@bp.route('/api/experiments/<experiment_id>/publish', methods=['GET'])
def publish_experiment(experiment_id):
    return ApiResponse.success(demo_experiment)


# ----- FILES -----

@bp.route('/api/experiments/<experiment_id>/files', methods=['GET'])
def list_experiment_files(experiment_id):

    return ApiResponse.success([
        {'name': 'SPC.tpr', 'url': f'http://localhost:8888/api/experiments/{experiment_id}/files/md.tpr', 'size': 123456},
        {'name': 'ABC.tpr', 'url': f'http://localhost:8888/api/experiments/{experiment_id}/files/md.tpr', 'size': 654321},
        {'name': 'trajectory.xtc', 'url': f'http://localhost:8888/api/experiments/{experiment_id}/files/sampled.xtc', 'size': 987654},
        {'name': 'structure.pdb', 'url': f'http://localhost:8888/api/experiments/{experiment_id}/files/minimal.pdb', 'size': 456789},
        {'name': 'structure.gro', 'url': f'/api/experiments/{experiment_id}/files/structure.gro', 'size': 321654},
    ])


@bp.route('/api/experiments/<experiment_id>/files/<path:path>', methods=['GET'])
def get_experiment_file(experiment_id, path: str):
    from pathlib import Path
    file_path = Path(__file__).parent / "_demo" / path
    return send_file(file_path, as_attachment=False)


if __name__ == '__main__':
    app = Flask(__name__)
    app.register_blueprint(bp)
    app.run(debug=True, host='0.0.0.0', port=8888)
