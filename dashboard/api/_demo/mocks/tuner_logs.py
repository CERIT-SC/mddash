"""
Tuner trial log mocking via module mutation.

Provides mock implementations for trial stdout/stderr endpoints
that return simulated GROMACS mdrun output.
"""

import logging

from clients import tuner

from ..state import demo_state

logger = logging.getLogger(__name__)

# Simulated GROMACS stdout template
_GMX_STDOUT_TEMPLATE = """\
:-) GROMACS - gmx mdrun, 2026.1 (-:

Executing on: {np} MPI ranks, {ntomp} OpenMP threads
Input file: {deffnm}.tpr
Output file: {deffnm}.log
Number of steps: {nsteps}

Starting simulation...
Step {step}, time {time} ps, performance: {performance:.3f} ns/day

Final performance: {performance:.3f} ns/day
Simulation completed successfully.
"""

# Simulated GROMACS stderr template (usually empty or warnings)
_GMX_STDERR_TEMPLATE = ""


def install_tuner_log_mocks() -> None:
    """Install tuner trial log mocks via module mutation."""
    tuner.gmx_get_trial_stdout = _get_trial_stdout
    tuner.gmx_get_trial_stderr = _get_trial_stderr


def _get_trial_stdout(job_id: str, trial_id: str) -> str:
    """
    Get mock stdout for a tuner trial.

    Args:
        job_id: The tuning job ID.
        trial_id: The trial ID within the job.

    Returns:
        Simulated GROMACS mdrun stdout output.
    """
    job_state = demo_state.tuner_jobs.get(job_id)

    if job_state is None:
        logger.warning("Trial stdout requested for unknown job %s", job_id)
        return ""

    trials = job_state.get("trials", [])
    trial = next((t for t in trials if isinstance(t, dict) and t.get("id") == trial_id), None)

    if trial is None:
        logger.warning("Trial stdout requested for unknown trial %s in job %s", trial_id, job_id)
        return ""

    # Return empty string if trial is still running
    if trial.get("status") == "RUNNING":
        return ""

    # Generate realistic-looking output
    performance = trial.get("performance", 50.0)
    np = trial.get("np", 2)
    ntomp = trial.get("ntomp", 4)
    nsteps = 25000

    # Calculate approximate step count based on performance
    step = nsteps
    time_ps = step * 0.002  # Approximate 2 fs per step

    return _GMX_STDOUT_TEMPLATE.format(
        np=np,
        ntomp=ntomp,
        deffnm="md",
        nsteps=nsteps,
        step=step,
        time=time_ps,
        performance=performance,
    )


def _get_trial_stderr(job_id: str, trial_id: str) -> str:
    """
    Get mock stderr for a tuner trial.

    Args:
        job_id: The tuning job ID.
        trial_id: The trial ID within the job.

    Returns:
        Simulated GROMACS mdrun stderr output (typically empty).
    """
    job_state = demo_state.tuner_jobs.get(job_id)

    if job_state is None:
        logger.warning("Trial stderr requested for unknown job %s", job_id)
        return ""

    trials = job_state.get("trials", [])
    trial = next((t for t in trials if isinstance(t, dict) and t.get("id") == trial_id), None)

    if trial is None:
        logger.warning("Trial stderr requested for unknown trial %s in job %s", trial_id, job_id)
        return ""

    # Stderr is typically empty for successful runs
    if trial.get("status") == "ERROR":
        return "Error: Simulation failed due to invalid parameters.\n"

    return _GMX_STDERR_TEMPLATE