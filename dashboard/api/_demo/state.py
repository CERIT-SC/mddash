"""
In-memory state management for demo API.
Stores experiments with their notebooks, tuner jobs, and gromacs jobs.
"""

import time
from datetime import datetime
from uuid import uuid4
import random


class DemoState:
    """Centralized state for demo API. Each experiment contains its notebook, tuner_jobs, and gromacs_jobs."""
    
    def __init__(self) -> None:
        self.experiments: dict[str, dict] = {}
        self.mdrepo_authenticated: bool = False
        self._init_demo_data()
    
    def _init_demo_data(self):
        """Initialize with some demo experiments."""
        # Experiment 1: Cancer cure (setup stage)
        exp1 = self.create_experiment(
            'aaaaa',
            'Cancer cure',
            "Created by uploading TPR file 'cancer_cure.tpr'."
        )
        
        # Experiment 2: HIV research (simulating stage)
        exp2 = self.create_experiment(
            'bbbbb',
            'HIV protein behavior research for drug development',
            "Created by downloading repository from 'https://zenodo.org/records/7261108'."
        )
        exp2['notebook']['status'] = 'RUNNING'
        exp2['tuner_jobs'].append(self._create_tuner_job('bbbbb', 'LSD.tpr', is_pending=False))
        exp2['tuner_jobs'].append(self._create_tuner_job('bbbbb', 'MDMA.tpr', is_pending=False, is_stopped=True))
        exp2['tuner_jobs'].append(self._create_tuner_job('bbbbb', 'Pending.tpr', is_pending=True))
        exp2['tuner_jobs'].append(self._create_tuner_job('bbbbb', 'Failed.tpr', is_pending=False, 
                                  error_message='TPR modification failed: Job tpr-mod-abcde-1234567890 failed'))
        exp2['gromacs_jobs'].append(self._create_gromacs_job('bbbbb', 'LSD.tpr', np=2, ntomp=8, nb='cpu', pme='cpu',
                                    status='RUNNING', nsteps=100000, nsteps_done=76543))
        exp2['gromacs_jobs'].append(self._create_gromacs_job('bbbbb', 'MDMA.tpr', np=8, ntomp=1, nb='gpu', pme='cpu',
                                    status='TERMINATED', nsteps=100000, nsteps_done=100000, performance=70.158))
        exp2['has_tpr_files'] = True
        
        # Experiment 3: Published experiment
        exp3 = self.create_experiment(
            'ccccc',
            'My first experiment',
            "Created by uploading TPR file 'my_first_experiment.tpr'.",
            mdrepo_id='xej9e-x3720'
        )
        exp3['notebook']['status'] = 'DOWN'
        exp3['gromacs_jobs'].append(self._create_gromacs_job('ccccc', 'output.tpr', np=4, ntomp=4, nb='cpu', pme='cpu',
                                    status='TERMINATED', nsteps=50000, nsteps_done=50000, performance=45.3))
        exp3['has_tpr_files'] = True

    def create_experiment(self, exp_id: str, name: str, source_message: str,
                         mdrepo_id: str | None = None) -> dict:
        """Create a new experiment with notebook."""
        now = datetime.now().isoformat()
        
        notebook = {
            'id': len(self.experiments) + 1,
            'experiment_id': exp_id,
            'token': str(uuid4()),
            'status': 'DOWN',
            'path': f'/__BASE_PATH__/notebook/{exp_id}/',
            'start_time': None,
        }
        
        experiment: dict[str, object] = {
            'id': exp_id,
            'created_at': now,
            'updated_at': now,
            'name': name,
            'source_message': source_message,
            'mdrepo_id': mdrepo_id,
            'mdrepo_record_url': f'https://workflow-repo.test.du.cesnet.cz/datasets/uploads/{mdrepo_id}' if mdrepo_id else None,
            'notebook': notebook,
            'tuner_jobs': [],
            'gromacs_jobs': [],
            'has_tpr_files': False,
        }
        
        self.experiments[exp_id] = experiment
        return experiment
    
    def _create_tuner_job(self, exp_id: str, tpr_name: str, is_pending: bool = True,
                         is_stopped: bool = False, error_message: str | None = None) -> dict:
        """Create a tuner job dict."""
        tuner_run_id = None if is_pending or error_message else str(uuid4())
        
        trials: list[dict] = []
        cluster_resources = 'Pending' if is_pending else ('Error' if error_message else '0/32 CPUs, 0/1 GPUs used')
        
        if not is_pending and not error_message and tuner_run_id:
            trials = [
                {'id': f'{tuner_run_id[:5]}_00000', 'status': 'RUNNING', 'np': 2, 'ntomp': 2, 
                 'nb': 'cpu', 'pme': 'cpu', 'performance': None, 'start_time': time.time()},
                {'id': f'{tuner_run_id[:5]}_00001', 'status': 'RUNNING', 'np': 2, 'ntomp': 8,
                 'nb': 'cpu', 'pme': 'cpu', 'performance': None, 'start_time': time.time()},
            ]
            if is_stopped:
                trials.append({
                    'id': f'{tuner_run_id[:5]}_00002', 'status': 'TERMINATED', 'np': 8, 'ntomp': 1,
                    'nb': 'gpu', 'pme': 'cpu', 'performance': 70.158, 'start_time': time.time() - 100
                })
        
        return {
            'id': self._get_next_tuner_id(),
            'tuner_run_id': tuner_run_id,
            'experiment_id': exp_id,
            'tpr_name': tpr_name,
            'is_pending': is_pending,
            'error_message': error_message,
            'created_at': datetime.now().isoformat(),
            'is_stopped': is_stopped,
            'start_time': None if is_pending else time.time(),
            'trials': trials,
            'cluster_resources': cluster_resources,
        }

    def _create_gromacs_job(self, exp_id: str, tpr_name: str, np: int, ntomp: int,
                           nb: str, pme: str, status: str = 'PENDING', nsteps: int = 100000,
                           nsteps_done: int = 0, performance: float | None = None,
                           extra_args: str = '') -> dict:
        """Create a gromacs job dict."""
        return {
            'id': self._get_next_gmx_id(),
            'experiment_id': exp_id,
            'created_at': datetime.now().isoformat(),
            'tpr_name': tpr_name,
            'job_name': f'gromacs-{uuid4()}',
            'pme': pme,
            'nb': nb,
            'np': np,
            'ntomp': ntomp,
            'extra_args': extra_args,
            'start_timestamp': int(time.time()) + 5,
            'finish_timestamp': int(time.time()) + random.randint(10**4, 10**6),
            'nsteps': nsteps,
            'performance': performance,
            'status': status,
            'nsteps_done': nsteps_done,
            'estimated_time': 0,
            'start_time': time.time(),
        }
    
    def get_experiment(self, exp_id: str) -> dict | None:
        """Get experiment with formatted data."""
        exp = self.experiments.get(exp_id)
        if not exp:
            return None
        
        exp_copy = exp.copy()
        
        # Calculate step and status dynamically
        step, status = self._step_status(exp)
        exp_copy['step'] = step
        exp_copy['status'] = status
        
        exp_copy['tuner_jobs'] = [self._format_tuner_job(tj) for tj in exp['tuner_jobs']]
        exp_copy['gromacs_jobs'] = [self._clean_gromacs_job(gj) for gj in exp['gromacs_jobs']]
        exp_copy['notebook'] = self._clean_notebook(exp['notebook'])
        
        return exp_copy
    
    def get_all_experiments(self) -> list[dict]:
        """Get all experiments with formatted data."""
        result = []
        for exp_id in self.experiments.keys():
            exp = self.get_experiment(exp_id)
            if exp:
                result.append(exp)
        return result
    
    def delete_experiment(self, exp_id: str) -> bool:
        """Delete experiment."""
        if exp_id not in self.experiments:
            return False
        del self.experiments[exp_id]
        return True
    
    def _format_tuner_job(self, tuner: dict) -> dict:
        """Format tuner job with summary and clean internal fields."""
        tuner_copy = tuner.copy()
        tuner_copy['summary'] = self._get_tuner_summary(tuner)
        tuner_copy.pop('start_time', None)
        
        tuner_copy['trials'] = [t.copy() for t in tuner['trials']]
        for trial in tuner_copy['trials']:
            trial.pop('start_time', None)
        
        return tuner_copy
    
    def _clean_gromacs_job(self, job: dict) -> dict:
        """Remove internal fields from gromacs job."""
        job_copy = job.copy()
        job_copy.pop('start_time', None)
        return job_copy
    
    def _clean_notebook(self, notebook: dict) -> dict:
        """Remove internal fields from notebook."""
        notebook_copy = notebook.copy()
        notebook_copy.pop('start_time', None)
        notebook_copy['path'] = f"/__BASE_PATH__/notebook/{notebook['experiment_id']}/?token={notebook['token']}"
        return notebook_copy
    
    def _get_next_tuner_id(self) -> int:
        """Get next tuner job ID."""
        max_id = 0
        for exp in self.experiments.values():
            for tj in exp['tuner_jobs']:
                max_id = max(max_id, tj['id'])
        return max_id + 1
    
    def _get_next_gmx_id(self) -> int:
        """Get next gromacs job ID."""
        max_id = 0
        for exp in self.experiments.values():
            for gj in exp['gromacs_jobs']:
                max_id = max(max_id, gj['id'])
        return max_id + 1
    
    def _step_status(self, exp: dict) -> tuple[int, str]:
        """
        Determine (step, status) based on current state.
        Mirrors the logic from models/experiment.py
        """
        # Step 5: Published (experiment has mdrepo_id)
        if exp.get('mdrepo_id'):
            return 5, 'published'

        # Step 4: Analyzing (experiment has terminated GROMACS job)
        if any(j['status'] == 'TERMINATED' for j in exp['gromacs_jobs']):
            return 4, 'analyzing'

        # NOTE: Step 3 is skipped because no action is required to progress from Analyze to Publish

        # Step 2: Running simulation (experiment has a GROMACS job)
        if exp['gromacs_jobs']:
            return 2, 'simulating'

        # Step 2: Tuning (experiment has terminated tuner job)
        tuner_jobs = exp['tuner_jobs']
        if any(self._get_tuner_summary(tj).get('TERMINATED', 0) > 0 for tj in tuner_jobs):
            return 2, 'tuning'

        # Step 1: Tuning (experiment has a tuner job)
        if tuner_jobs:
            return 1, 'tuning'

        # Step 1: Setup complete (directory contains a TPR file)
        if exp.get('has_tpr_files'):
            return 1, 'setup complete'

        return 0, 'setup'
    
    def _get_tuner_summary(self, tuner: dict) -> dict[str, int]:
        """Get summary of tuner job statuses."""
        summary = {}
        
        if tuner['is_pending']:
            summary['PENDING'] = 1
        elif tuner['error_message']:
            summary['ERROR'] = 1
        else:
            for trial in tuner['trials']:
                status = trial['status']
                summary[status] = summary.get(status, 0) + 1
        
        return summary


# Global state instance
state = DemoState()
