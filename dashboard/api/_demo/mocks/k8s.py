"""
Kubernetes client mocking via module mutation.

The kubernetes library doesn't use requests internally, so we replace
module-level functions instead of using HTTP mocking.

Analysis jobs fetch real data from MDposit API for realistic demo data.
"""

import json
import logging
import re
import threading
import time

import requests
from clients import k8s
from config import DATA_DIR
from enums import JobStatus, PodStatus
from models.analysis_job import ANALYSIS_RESULT_PREFIX, ANALYSIS_RESULT_SUFFIX, MWF_DIR

from ..state import demo_state

logger = logging.getLogger(__name__)

# Analysis job duration in seconds
ANALYSIS_JOB_DURATION_SEC = 3.0

# MDposit API endpoint for analysis data
MDPOSIT_ANALYSES_URL = "https://mdposit.mddbr.eu/api/rest/v1/projects/MD-A003ZT.2/analyses"

# MDposit uses different endpoint names for some analysis types
_MDPOSIT_NAME_MAP: dict[str, str] = {
    "dist": "dist-perres",
    "inter": "interactions",
    "linter": "lipid-inter",
    "lorder": "lipid-order",
    "pairwise": "rmsd-pairwise",
    "perres": "rmsd-perres",
    "rmsf": "fluctuation",
    "sas": "sasa",
    "tmscore": "tmscores",
}


def install_k8s_mocks() -> None:
    """Install Kubernetes client mocks via module mutation."""
    k8s.get_pod_status = _get_pod_status  # type: ignore
    k8s.create_notebook_pod = _create_notebook_pod  # type: ignore
    k8s.delete_pod = _delete_pod  # type: ignore
    k8s.create_service = _create_service  # type: ignore
    k8s.delete_service = _delete_service  # type: ignore
    k8s.get_pod_resource_requests = _get_pod_resource_requests  # type: ignore
    k8s.create_job = _create_job  # type: ignore
    k8s.get_job_status = _get_job_status  # type: ignore
    k8s.delete_job = _delete_job  # type: ignore
    k8s.get_job_logs = _get_job_logs  # type: ignore


def _get_pod_status(name: str) -> PodStatus:
    """
    Get mock pod status.

    Returns:
        The pod status for the given notebook name.
    """
    if not name.startswith("notebook-"):
        return PodStatus.DOWN
    experiment_id = name.removeprefix("notebook-")
    return demo_state.notebook_status.get(experiment_id, PodStatus.DOWN)


def _create_notebook_pod(
    name: str,
    experiment_id: str,
    _prefix: str,
    _token: str,
    notebook_resources: dict | None = None,  # noqa: ARG001
    gpu: bool = False,  # noqa: ARG001
    tier: str | None = None,  # noqa: ARG001
) -> None:
    """Create a mock notebook pod."""
    logger.debug("Mock creating notebook pod %s for experiment %s", name, experiment_id)
    demo_state.notebook_status[experiment_id] = PodStatus.RUNNING


def _delete_pod(name: str) -> None:
    """Delete a mock pod."""
    if not name.startswith("notebook-"):
        return
    experiment_id = name.removeprefix("notebook-")
    demo_state.notebook_status[experiment_id] = PodStatus.DOWN


def _create_service(name: str, target_name: str) -> None:  # noqa: ARG001
    """Create a mock service (no-op)."""
    logger.debug("Mock creating service %s", name)


def _delete_service(name: str) -> None:
    """Delete a mock service (no-op)."""
    logger.debug("Mock deleting service %s", name)


def _get_pod_resource_requests() -> dict[str, int]:
    """
    Get mock pod resource requests.

    Returns:
        Dict with cpu and memory values.
    """
    return {
        "cpu": 768,  # millicores
        "memory": 7_500_000_000,  # bytes (~7.5 GiB)
    }


def _create_job(
    name: str,
    image: str,  # noqa: ARG001
    experiment_id: str,
    command: str,
    resources: dict | None = None,  # noqa: ARG001
) -> None:
    """Create a mock analysis job."""
    # Extract the mwf analysis name from the "-i <name>" flag at the end of the command
    match = re.search(r"-i\s+(\w+)\s*$", command)
    analysis_name = match.group(1) if match else ""

    demo_state.analysis_jobs[name] = {
        "status": JobStatus.RUNNING.value,
        "experiment_id": experiment_id,
        "analysis_name": analysis_name,
        "created_at": time.time(),
    }

    # Start background thread to fetch real analysis data from MDposit
    thread = threading.Thread(
        target=_fetch_and_store_analysis,
        args=(name, experiment_id, analysis_name),
        daemon=True,
    )
    thread.start()


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


def _get_job_logs(name: str, tail_lines: int = 200) -> str:  # noqa: ARG001
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
    if status == JobStatus.TERMINATED.value:
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


def _mdposit_get(path: str) -> requests.Response:
    """
    Fetch analysis data from MDposit API.

    Returns:
        The HTTP response from MDposit.
    """
    headers = {"Accept": "application/json"}
    return requests.get(f"{MDPOSIT_ANALYSES_URL}/{path}", headers=headers, timeout=30)


def _fetch_and_store_analysis(job_name: str, experiment_id: str, analysis_name: str) -> None:
    """Fetch analysis data from MDposit and write result files, then mark the job done."""
    time.sleep(ANALYSIS_JOB_DURATION_SEC)
    try:
        mdposit_name = _MDPOSIT_NAME_MAP.get(analysis_name, analysis_name)
        response = _mdposit_get(mdposit_name)
        if not response.ok:
            logger.warning(
                "MDposit returned %s for analysis '%s' (endpoint: '%s')",
                response.status_code,
                analysis_name,
                mdposit_name,
            )
            demo_state.analysis_jobs[job_name]["status"] = JobStatus.ERROR.value
            return

        data = response.json()
        mwf_dir = DATA_DIR / experiment_id / MWF_DIR
        mwf_dir.mkdir(parents=True, exist_ok=True)

        # Use the mwf output name (= MDposit endpoint name), not the AnalysisType value.
        # mwf uses different output file names for some analyses (e.g. "-i inter" produces
        # mda.interactions.json, "-i rmsf" produces mda.fluctuation.json).
        primary_filename = f"{ANALYSIS_RESULT_PREFIX}{mdposit_name.replace('-', '_')}{ANALYSIS_RESULT_SUFFIX}"
        (mwf_dir / primary_filename).write_text(json.dumps(data), encoding="utf-8")

        # If the result is a summary list pointing to variants, fetch each one
        if isinstance(data, list):
            for item in data:
                if not isinstance(item, dict):
                    continue
                variant_name = item.get("analysis", "")
                if not variant_name:
                    continue
                variant_response = _mdposit_get(variant_name)
                if variant_response.ok:
                    variant_filename = (
                        f"{ANALYSIS_RESULT_PREFIX}{variant_name.replace('-', '_')}{ANALYSIS_RESULT_SUFFIX}"
                    )
                    (mwf_dir / variant_filename).write_text(json.dumps(variant_response.json()), encoding="utf-8")

        demo_state.analysis_jobs[job_name]["status"] = JobStatus.TERMINATED.value
        logger.debug("Analysis job %s completed with MDposit data", job_name)

    except Exception:
        logger.exception("Failed to fetch analysis '%s' for demo job %s", analysis_name, job_name)
        if job_name in demo_state.analysis_jobs:
            demo_state.analysis_jobs[job_name]["status"] = JobStatus.ERROR.value
