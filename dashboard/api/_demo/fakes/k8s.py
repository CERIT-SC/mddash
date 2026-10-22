"""
In-memory Kubernetes for the demo: notebook pods, analysis Jobs, and upload/archive worker Jobs.

Worker Jobs finish on daemon threads; analysis Jobs finish with real MDPosit data.
"""

import logging
import re
import threading
import time
from datetime import datetime, timezone
from shutil import rmtree
from types import SimpleNamespace

from clients.k8s import K8sClient
from core.cache import mdrepo_status_cache
from core.config import DATA_DIR
from core.enums import JobStatus, NotebookTier, PodStatus
from modules.archive.status import ArchiveStatus
from modules.archive.status import write_status as write_archive_status
from modules.publishing.status import UploadStatus, read_status
from modules.publishing.status import write_status as write_upload_status
from modules.publishing.submission import EXPERIMENT_LABEL

from ..analysis_data import start_analysis_thread
from ..state import E2E, demo_state

logger = logging.getLogger(__name__)

# Analysis job duration in seconds (0.5s in E2E mode)
ANALYSIS_JOB_DURATION_SEC = 0.5 if E2E else 3.0

# MDRepo upload job duration in seconds (0.5s in E2E mode)
UPLOAD_JOB_DURATION_SEC = 0.5 if E2E else 4.0


def _create_job_raw(manifest: dict) -> None:
    """Simulate the MDRepo upload and archive workers: mark done after a short delay."""
    try:
        experiment_id = manifest["metadata"]["labels"][EXPERIMENT_LABEL]
        job_name = manifest["metadata"]["name"]
        args = manifest["spec"]["template"]["spec"]["containers"][0]["args"]
    except (KeyError, IndexError, ValueError):
        return

    # Archive worker args start with the mode; the upload worker's with --experiment-id.
    if args and args[0] in {"archive", "restore", "purge"}:
        try:
            mode, attempt_id = args[0], args[args.index("--attempt-id") + 1]
        except (IndexError, ValueError):
            return
        demo_state.upload_jobs[job_name] = experiment_id
        threading.Thread(
            target=_finish_archive_job, args=(job_name, mode, experiment_id, attempt_id), daemon=True
        ).start()
        return

    try:
        mdrepo_id = args[args.index("--mdrepo-id") + 1]
    except (IndexError, ValueError):
        return
    demo_state.upload_jobs[job_name] = experiment_id
    threading.Thread(target=_finish_upload_job, args=(job_name, experiment_id, mdrepo_id), daemon=True).start()


ARCHIVE_JOB_DURATION_SEC = 4.0


def _finish_archive_job(job_name: str, mode: str, experiment_id: str, attempt_id: str) -> None:
    """
    Stand-in for the archive worker.

    Archive deletes the dir like a verified worker would; restore fabricates a
    minimal dir (there is no demo S3 to fetch from).
    """
    time.sleep(ARCHIVE_JOB_DURATION_SEC)
    demo_state.upload_jobs.pop(job_name, None)

    exp_dir = DATA_DIR / experiment_id
    if mode == "archive":
        write_archive_status(
            ArchiveStatus(attempt_id=attempt_id, state="completed", direction="archive"), experiment_id, DATA_DIR
        )
        rmtree(exp_dir, ignore_errors=True)
    elif mode == "restore":
        exp_dir.mkdir(parents=True, exist_ok=True)
        (exp_dir / "RESTORED.txt").write_text("Restored from the demo archive (contents simulated).\n")
        write_archive_status(
            ArchiveStatus(attempt_id=attempt_id, state="completed", direction="restore"), experiment_id, DATA_DIR
        )


def _finish_upload_job(job_name: str, experiment_id: str, mdrepo_id: str) -> None:
    time.sleep(UPLOAD_JOB_DURATION_SEC)
    demo_state.upload_jobs.pop(job_name, None)

    queued = read_status(experiment_id, DATA_DIR)
    exp_dir = DATA_DIR / experiment_id
    files = [p for p in exp_dir.rglob("*") if p.is_file()]
    total_bytes = sum(p.stat().st_size for p in files)
    write_upload_status(
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

    # Stands in for MDRepo-UI finalization, which the demo lacks; the cache
    # bust makes the next serialization re-sync at once, not after the TTL.
    demo_state.mdrepo_records[mdrepo_id] = True
    mdrepo_status_cache.clear()


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
) -> str:
    """Create a mock notebook pod."""
    logger.debug("Mock creating notebook pod %s for experiment %s", name, experiment_id)
    demo_state.notebook_status[experiment_id] = PodStatus.RUNNING
    demo_state.notebook_started_at[experiment_id] = datetime.now(timezone.utc)
    return f"demo-uid-{name}"


def _delete_pod(name: str) -> None:
    """Delete a mock pod."""
    if not name.startswith("notebook-"):
        return
    experiment_id = name.removeprefix("notebook-")
    demo_state.notebook_status[experiment_id] = PodStatus.DOWN
    demo_state.notebook_started_at.pop(experiment_id, None)


def _create_service(name: str, target_name: str, target_uid: str) -> None:  # ruff:ignore[unused-function-argument]
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


class DemoK8sClient(K8sClient):
    """K8sClient answering from `demo_state`; it never loads cluster config."""

    async def get_pod_info(self, name: str) -> "tuple[PodStatus, datetime | None]":
        """Notebook pod (status, start time) from the demo state."""
        return _get_pod_info(name)

    async def create_notebook_pod(
        self,
        name: str,
        experiment_id: str,
        prefix: str,
        token: str,
        notebook_resources: dict | None = None,
        gpu: bool = False,
        tier: NotebookTier | None = None,
    ) -> str:
        """Mark the notebook running."""
        return _create_notebook_pod(name, experiment_id, prefix, token, notebook_resources, gpu, tier)

    async def delete_pod(self, name: str) -> None:
        """Mark the notebook down."""
        _delete_pod(name)

    async def create_service(self, name: str, target_name: str, target_uid: str) -> None:
        """No-op: notebook routing is not simulated."""
        _create_service(name, target_name, target_uid)

    async def delete_service(self, name: str) -> None:
        """No-op: notebook routing is not simulated."""
        _delete_service(name)

    async def create_job(
        self, name: str, image: str, experiment_id: str, command: str, resources: dict | None = None
    ) -> None:
        """Start an analysis Job that completes on a thread."""
        _create_job(name, image, experiment_id, command, resources)

    async def get_job_status(self, name: str) -> JobStatus:
        """Analysis Job status from the demo state."""
        return _get_job_status(name)

    async def delete_job(self, name: str) -> None:
        """Forget an analysis Job."""
        _delete_job(name)

    async def get_job_logs(self, name: str, tail_lines: int = 200) -> str:
        """Canned analysis Job logs."""
        return _get_job_logs(name, tail_lines)

    async def check_quota_headroom(
        self,
        cpu_request: int,  # ruff:ignore[unused-method-argument]
        memory_request: int,  # ruff:ignore[unused-method-argument]
        cpu_limit: int = 0,  # ruff:ignore[unused-method-argument]
        memory_limit: int = 0,  # ruff:ignore[unused-method-argument]
    ) -> str | None:
        """Report quota headroom: the demo namespace never runs out."""
        return None

    async def count_notebook_pods(self) -> int:
        """Count the running demo notebooks."""
        return sum(1 for status in demo_state.notebook_status.values() if status == PodStatus.RUNNING)

    async def ping_resource(self, resource_type: str, name: str) -> bool:  # ruff:ignore[unused-method-argument]
        """Report every resource as existing."""
        return True

    async def create_job_raw(self, manifest: dict) -> None:
        """Run an upload/archive worker Job on a thread."""
        _create_job_raw(manifest)

    async def wait_for_pod_admission(
        self,
        label_selector: str,  # ruff:ignore[unused-method-argument]
        max_wait: int = 30,  # ruff:ignore[unused-method-argument]
    ) -> bool:
        """Admit worker pods at once."""
        return True

    async def read_job(self, name: str) -> object | None:
        """Upload/archive worker Job while its thread runs."""
        return _read_upload_job(name)

    async def delete_job_foreground(self, name: str) -> None:
        """Forget a worker Job."""
        demo_state.upload_jobs.pop(name, None)

    async def wait_for_resource_absence(
        self,
        resource_type: str,  # ruff:ignore[unused-method-argument]
        name: str,  # ruff:ignore[unused-method-argument]
        max_wait: int = 30,  # ruff:ignore[unused-method-argument]
    ) -> bool:
        """Report deleted resources as gone at once."""
        return True
