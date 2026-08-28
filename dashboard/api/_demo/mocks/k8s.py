"""
Kubernetes client mocking via module mutation.

The kubernetes library doesn't use requests internally, so we replace
module-level functions instead of using HTTP mocking.

Analysis jobs fetch real data from MDposit API for realistic demo data.
"""

import logging
import re
import threading
import time
from datetime import datetime, timezone
from types import SimpleNamespace

from clients import k8s
from config import DATA_DIR
from enums import JobStatus, PodStatus

from ..analysis_data import start_analysis_thread
from ..state import demo_state

logger = logging.getLogger(__name__)

# Analysis job duration in seconds
ANALYSIS_JOB_DURATION_SEC = 3.0

# MDRepo upload job duration in seconds
UPLOAD_JOB_DURATION_SEC = 4.0


def install_k8s_mocks() -> None:
    """Install Kubernetes client mocks via module mutation."""
    # The single pod read notebooks use for both status and start time.
    k8s.get_pod_info = _get_pod_info  # type: ignore
    k8s.create_notebook_pod = _create_notebook_pod  # type: ignore
    k8s.delete_pod = _delete_pod  # type: ignore
    k8s.create_service = _create_service  # type: ignore
    k8s.delete_service = _delete_service  # type: ignore

    k8s.create_job = _create_job  # type: ignore
    k8s.get_job_status = _get_job_status  # type: ignore
    k8s.delete_job = _delete_job  # type: ignore
    k8s.get_job_logs = _get_job_logs  # type: ignore
    k8s.check_quota_headroom = lambda *_a, **_k: None  # type: ignore
    k8s.count_notebook_pods = lambda: sum(1 for s in demo_state.notebook_status.values() if s == PodStatus.RUNNING)  # type: ignore
    k8s.ping_resource = lambda *_a, **_k: True  # type: ignore
    k8s.create_job_raw = _create_job_raw  # type: ignore
    k8s.wait_for_pod_admission = lambda *_a, **_k: True  # type: ignore
    k8s.read_job = _read_upload_job  # type: ignore
    k8s.delete_job_foreground = lambda name: demo_state.upload_jobs.pop(name, None)  # type: ignore
    k8s.wait_for_resource_absence = lambda *_a, **_k: True  # type: ignore


def _create_job_raw(manifest: dict) -> None:
    """Simulate the MDRepo upload worker: mark done after a short delay."""
    try:
        from upload.submission import EXPERIMENT_LABEL  # ruff:ignore[import-outside-top-level]

        experiment_id = manifest["metadata"]["labels"][EXPERIMENT_LABEL]
        job_name = manifest["metadata"]["name"]
    except (KeyError, ImportError):
        return

    demo_state.upload_jobs[job_name] = experiment_id
    threading.Thread(target=_finish_upload_job, args=(job_name, experiment_id), daemon=True).start()


def _finish_upload_job(job_name: str, experiment_id: str) -> None:
    from upload.status import UploadStatus, write_status  # ruff:ignore[import-outside-top-level]

    time.sleep(UPLOAD_JOB_DURATION_SEC)
    demo_state.upload_jobs.pop(job_name, None)

    from upload.status import read_status  # ruff:ignore[import-outside-top-level]

    queued = read_status(experiment_id, DATA_DIR)
    exp_dir = DATA_DIR / experiment_id
    files = [p for p in exp_dir.rglob("*") if p.is_file()]
    total_bytes = sum(p.stat().st_size for p in files)
    write_status(
        UploadStatus(
            attempt_id=queued.attempt_id if queued else "demo-attempt",
            state="completed",
            total_files=len(files),
            completed_files=len(files),
            total_bytes=total_bytes,
            completed_bytes=total_bytes,
        ),
        experiment_id,
        DATA_DIR,
    )


def _read_upload_job(name: str) -> SimpleNamespace | None:
    if name not in demo_state.upload_jobs:
        return None
    return SimpleNamespace(status=SimpleNamespace(active=1))


def _get_pod_info(name: str) -> tuple[PodStatus, "datetime | None"]:
    """Mock (status, start_time) per notebook name; start time is None while DOWN."""
    if not name.startswith("notebook-"):
        return PodStatus.DOWN, None
    experiment_id = name.removeprefix("notebook-")
    status = demo_state.notebook_status.get(experiment_id, PodStatus.DOWN)
    started = demo_state.notebook_started_at.get(experiment_id) if status != PodStatus.DOWN else None
    return status, started


def _create_notebook_pod(
    name: str,
    experiment_id: str,
    _prefix: str,
    _token: str,
    notebook_resources: dict | None = None,  # ruff:ignore[unused-function-argument]
    gpu: bool = False,  # ruff:ignore[unused-function-argument]
    tier: str | None = None,  # ruff:ignore[unused-function-argument]
) -> None:
    """Create a mock notebook pod."""
    logger.debug("Mock creating notebook pod %s for experiment %s", name, experiment_id)
    demo_state.notebook_status[experiment_id] = PodStatus.RUNNING
    demo_state.notebook_started_at[experiment_id] = datetime.now(timezone.utc)


def _delete_pod(name: str) -> None:
    """Delete a mock pod."""
    if not name.startswith("notebook-"):
        return
    experiment_id = name.removeprefix("notebook-")
    demo_state.notebook_status[experiment_id] = PodStatus.DOWN
    demo_state.notebook_started_at.pop(experiment_id, None)


def _create_service(name: str, target_name: str) -> None:  # ruff:ignore[unused-function-argument]
    """Create a mock service (no-op)."""
    logger.debug("Mock creating service %s", name)


def _delete_service(name: str) -> None:
    """Delete a mock service (no-op)."""
    logger.debug("Mock deleting service %s", name)


def _create_job(
    name: str,
    image: str,  # ruff:ignore[unused-function-argument]
    experiment_id: str,
    command: str,
    resources: dict | None = None,  # ruff:ignore[unused-function-argument]
) -> None:
    """Create a mock analysis job."""
    # Extract the mwf analysis name from the "-i <name>" flag at the end of the command
    match = re.search(r"-i\s+(\w+)\s*$", command)
    analysis_name = match.group(1) if match else ""

    # Extract simulation_path from the "-md analysis/mwf/<stem>" flag — the
    # stem already ends in ".simulation", so the manifest is stem + ".json".
    md_match = re.search(r"-md\s+analysis/mwf/(\S+)", command)
    simulation_stem = md_match.group(1) if md_match else ""
    simulation_path = f"{simulation_stem}.json" if simulation_stem else ""

    demo_state.analysis_jobs[name] = {
        "status": JobStatus.RUNNING.value,
        "experiment_id": experiment_id,
        "analysis_name": analysis_name,
        "simulation_path": simulation_path,
        "created_at": time.time(),
    }

    # Job lifecycle: finish with real MDPosit outputs after the mock runtime.
    start_analysis_thread(name, experiment_id, simulation_path, analysis_name, delay_sec=ANALYSIS_JOB_DURATION_SEC)


def _get_job_status(name: str) -> JobStatus:
    """
    Get mock job status.

    Returns:
        The job status for the given job name.
    """
    job_data = demo_state.analysis_jobs.get(name)
    if job_data is None:
        return JobStatus.UNKNOWN
    try:
        return JobStatus(job_data.get("status", JobStatus.UNKNOWN.value))
    except ValueError:
        return JobStatus.UNKNOWN


def _delete_job(name: str) -> None:
    """Delete a mock job."""
    demo_state.analysis_jobs.pop(name, None)


def _get_job_logs(name: str, tail_lines: int = 200) -> str:  # ruff:ignore[unused-function-argument]
    """
    Get mock job logs.

    Returns:
        Mock log output for the job.
    """
    job_data = demo_state.analysis_jobs.get(name)
    if job_data is None:
        logger.warning("get_job_logs: job '%s' not in demo_state", name)
        return ""

    status = job_data.get("status", "")
    if status == JobStatus.FINISHED.value:
        return (
            "Running MDDB workflow\n"
            "Fetching analysis data...\n"
            "Processing results...\n"
            "Writing output files...\n"
            "Analysis completed successfully."
        )
    if status == JobStatus.ERROR.value:
        return "Running MDDB workflow\nError: Failed to fetch analysis data."
    return "Running MDDB workflow\nFetching analysis data..."
