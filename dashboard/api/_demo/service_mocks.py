import json
import logging
import re
import shutil
import threading
import time
from datetime import datetime
from http import HTTPStatus
from pathlib import Path
from typing import Any
from uuid import uuid4

import models.experiment as experiment_model
import requests

# Capture the real requests.get before install_mocks() replaces it globally.
# install_mocks() does `experiment_model.requests.get = ...` which mutates the
# shared requests module object, so any later call to `requests.get` would hit
# the fake function instead of the real HTTP stack.
_real_requests_get = requests.get

import routes.mdrepo as mdrepo_routes
from clients import caddy, k8s, mdrepo, mdrun, tuner
from config import DATA_DIR, MDREPO_RECORD_NAME, MDREPO_URL
from enums import JobStatus, PodStatus
from extensions import db
from models import GromacsJob
from models.analysis_job import ANALYSIS_RESULT_PREFIX, ANALYSIS_RESULT_SUFFIX, MWF_DIR

from .files import (
    DEFAULT_PDB_FILE,
    DEFAULT_TPR_FILE,
    DEFAULT_XTC_FILE,
    append_gmx_log_template_until,
    build_demo_archive_bytes,
    gmx_log_template_line_count,
    write_finished_gmx_log,
    write_running_gmx_log,
)
from .state import demo_state

logger = logging.getLogger(__name__)

MDPOSIT_ANALYSES_URL = "https://mdposit.mddbr.eu/api/rest/v1/projects/MD-A003ZT.2/analyses"
ANALYSIS_JOB_DURATION_SEC = 3.0

# MDposit uses different endpoint names for some analysis types.
# Keys are AnalysisType values; values are the corresponding MDposit path segments.
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

DEFAULT_GMX_NSTEPS = 100_000
DEFAULT_GMX_DURATION_SEC = 30.0
DEFAULT_TUNER_MAX_TRIALS = 3
TUNER_TRIAL_DURATION_SEC = 10.0


class SimpleResponse:
    def __init__(self, status_code: int, payload: dict | None = None, content: bytes = b"") -> None:
        self.status_code = status_code
        self._payload = payload
        self.content = content
        self.text = json.dumps(payload) if payload is not None else ""

    @property
    def ok(self) -> bool:
        return HTTPStatus.OK <= self.status_code < HTTPStatus.MULTIPLE_CHOICES

    def json(self) -> dict:
        return self._payload or {}


def install_mocks() -> None:
    experiment_model.download_git_repo = _fake_download_git_repo
    experiment_model.requests.get = _fake_experiment_requests_get

    k8s.get_pod_status = _k8s_get_pod_status
    k8s.create_notebook_pod = _k8s_create_notebook_pod
    k8s.delete_pod = _k8s_delete_pod
    k8s.create_service = _k8s_create_service
    k8s.delete_service = _k8s_delete_service
    k8s.get_pod_resource_requests = _k8s_get_pod_resource_requests
    k8s.create_job = _k8s_create_job
    k8s.get_job_status = _k8s_get_job_status
    k8s.delete_job = _k8s_delete_job
    k8s.get_job_logs = _k8s_get_job_logs

    caddy.add_proxy_route = _caddy_add_proxy_route
    caddy.remove_route = _caddy_remove_route

    mdrun.create_job = _mdrun_create_job
    mdrun.get_job = _mdrun_get_job
    mdrun.delete_job = _mdrun_delete_job

    tuner.run_submit = _tuner_run_submit
    tuner.poll_status = _tuner_poll_status
    tuner.delete_job = _tuner_delete_job

    mdrepo.create_experiment = _mdrepo_create_experiment
    mdrepo.check_experiment_status = _mdrepo_check_experiment_status
    mdrepo.start_upload_worker = _mdrepo_start_upload_worker

    mdrepo_routes.requests.get = _fake_mdrepo_requests_get
    mdrepo_routes.requests.post = _fake_mdrepo_requests_post


def _fake_download_git_repo(repo_url: str, output_dir: Path, access_token: str | None = None) -> None:  # noqa: ARG001
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "README.md").write_text(
        f"Demo notebooks repository mirror for {repo_url}\n",
        encoding="utf-8",
    )
    shutil.copy2(DEFAULT_TPR_FILE, output_dir / "md.tpr")
    shutil.copy2(DEFAULT_XTC_FILE, output_dir / "trajectory.xtc")
    shutil.copy2(DEFAULT_PDB_FILE, output_dir / "input.pdb")


def _fake_experiment_requests_get(url: str, timeout: int = 30) -> SimpleResponse:  # noqa: ARG001
    if "files.rcsb.org/download/" in url and url.endswith(".pdb"):
        return SimpleResponse(200, content=DEFAULT_PDB_FILE.read_bytes())

    if "zenodo.org/api/records/" in url and url.endswith("/files-archive"):
        return SimpleResponse(200, content=build_demo_archive_bytes())

    return SimpleResponse(404)


def _fake_mdrepo_requests_get(url: str, headers: dict | None = None, timeout: int = 10) -> SimpleResponse:  # noqa: ARG001
    token = (headers or {}).get("Authorization", "")
    if url.endswith("/api/me"):
        if token.startswith("Bearer demo"):
            return SimpleResponse(200, payload={"user": "demo"})
        return SimpleResponse(401, payload={"message": "Unauthorized"})
    return SimpleResponse(404)


def _fake_mdrepo_requests_post(url: str, data: dict | None = None, timeout: int = 30) -> SimpleResponse:  # noqa: ARG001
    if url.endswith("/oauth/token"):
        payload = {
            "access_token": "demo-access-token",
            "refresh_token": "demo-refresh-token",
            "expires_in": 3600,
        }
        return SimpleResponse(200, payload=payload)
    return SimpleResponse(404, payload={"message": "Not found"})


def _k8s_get_pod_status(name: str) -> PodStatus:
    if not name.startswith("notebook-"):
        return PodStatus.DOWN
    experiment_id = name.removeprefix("notebook-")
    return demo_state.notebook_status.get(experiment_id, PodStatus.DOWN)


def _k8s_create_notebook_pod(name: str, experiment_id: str, prefix: str, token: str) -> None:  # noqa: ARG001
    demo_state.notebook_status[experiment_id] = PodStatus.RUNNING


def _k8s_delete_pod(name: str) -> None:
    if not name.startswith("notebook-"):
        return
    experiment_id = name.removeprefix("notebook-")
    demo_state.notebook_status[experiment_id] = PodStatus.DOWN


def _k8s_create_service(name: str, pod_name: str) -> None:  # noqa: ARG001
    return


def _k8s_delete_service(name: str) -> None:  # noqa: ARG001
    return


def _k8s_get_pod_resource_requests() -> dict:
    return {
        "cpu": 768,
        "memory": 7_500_000_000,
    }


def _caddy_add_proxy_route(path: str, upstream: str, route_id: str | None = None) -> str:  # noqa: ARG001
    return route_id or f"route-{uuid4()}"


def _caddy_remove_route(route_id: str) -> bool:  # noqa: ARG001
    return True


def _mdrun_create_job(
    experiment_id: str,
    tpr_name: str,
    bucket_name: str,
    pme: str,
    nb: str,
    np: int,
    ntomp: int,
    extra_args: str = "",
) -> dict:
    job_id = f"demo-gmx-{uuid4()}"
    template_line_count = gmx_log_template_line_count()
    initial_line_index = write_running_gmx_log(experiment_id, Path(tpr_name).stem)
    demo_state.mdrun_jobs[job_id] = {
        "status": JobStatus.RUNNING.value,
        "experiment_id": experiment_id,
        "tpr_name": tpr_name,
        "nsteps": DEFAULT_GMX_NSTEPS,
        "log_line_index": initial_line_index,
        "log_total_lines": template_line_count,
        "created_at": time.time(),
        "duration_sec": DEFAULT_GMX_DURATION_SEC,
    }
    return {
        "id": job_id,
        "status": JobStatus.RUNNING.value,
        "bucket_name": bucket_name,
        "pme": pme,
        "nb": nb,
        "np": np,
        "ntomp": ntomp,
        "extra_args": extra_args,
    }


def _mdrun_get_job(job_id: str) -> dict:
    job_data = demo_state.mdrun_jobs.get(job_id)
    if job_data is None:
        gmx_job = GromacsJob.query.filter_by(id=job_id).first()
        if gmx_job is None:
            return {
                "id": job_id,
                "status": JobStatus.UNKNOWN.value,
            }

        status = JobStatus.TERMINATED.value if gmx_job._finish_timestamp else JobStatus.RUNNING.value  # noqa: SLF001
        job_data = {
            "status": status,
            "experiment_id": gmx_job.experiment_id,
            "tpr_name": gmx_job.tpr_name,
            "nsteps": gmx_job._nsteps or DEFAULT_GMX_NSTEPS,  # noqa: SLF001
            "log_line_index": 0,
            "log_total_lines": gmx_log_template_line_count(),
            "created_at": float(gmx_job._start_timestamp or time.time()),  # noqa: SLF001
            "duration_sec": DEFAULT_GMX_DURATION_SEC,
        }
        demo_state.mdrun_jobs[job_id] = job_data

    _advance_gmx_job(job_id, job_data)
    status = str(job_data.get("status", JobStatus.UNKNOWN.value))
    return {
        "id": job_id,
        "status": status,
    }


def _mdrun_delete_job(job_id: str) -> None:
    demo_state.mdrun_jobs.pop(job_id, None)


def _tuner_run_submit(tpr_path: Path, nsteps: int = 25000, extra_args: str = "") -> dict:  # noqa: ARG001
    run_id = f"demo-tuner-{uuid4()}"
    started_at = time.time()
    demo_state.tuner_jobs[run_id] = {
        "status": JobStatus.RUNNING.value,
        "created_at": started_at,
        "max_trials": DEFAULT_TUNER_MAX_TRIALS,
        "trials": [
            {
                "id": f"{run_id[:10]}-00000",
                "status": JobStatus.RUNNING.value,
                "np": 2,
                "ntomp": 4,
                "nb": "cpu",
                "pme": "cpu",
                "performance": None,
                "started_at": started_at,
            }
        ],
    }
    return {"id": run_id}


def _tuner_poll_status(job_id: str) -> dict:
    status = demo_state.tuner_jobs.get(job_id)
    if status is None:
        return {"status": JobStatus.UNKNOWN.value, "trials": []}

    _advance_tuner_status(status)
    trials = status.get("trials")
    if not isinstance(trials, list):
        trials = []
    return {
        "status": str(status.get("status", JobStatus.UNKNOWN.value)),
        "trials": [_public_trial(t) for t in trials if isinstance(t, dict)],
    }


def _tuner_delete_job(job_id: str) -> dict:
    demo_state.tuner_jobs.pop(job_id, None)
    return {"id": job_id}


def _mdrepo_create_experiment(access_token: str, community: str, metadata: dict) -> dict:  # noqa: ARG001
    record_id = "8gahj-dh519"
    demo_state.mdrepo_counter += 1
    demo_state.mdrepo_records[record_id] = False
    return {
        "id": record_id,
        "created": datetime.now().isoformat(),
        "updated": datetime.now().isoformat(),
        "links": {
            "self_html": f"{MDREPO_URL}/{MDREPO_RECORD_NAME}/records/{record_id}",
            "edit_html": f"{MDREPO_URL}/{MDREPO_RECORD_NAME}/uploads/{record_id}",
        },
        "state": "draft",
    }


def _mdrepo_check_experiment_status(access_token: str, experiment_id: str) -> bool | None:  # noqa: ARG001
    return demo_state.mdrepo_records.get(experiment_id)


def _mdrepo_start_upload_worker(access_token: str, experiment_id: str, experiment_dir: Path) -> threading.Thread:  # noqa: ARG001
    def _worker() -> None:
        time.sleep(0.1)

    thread = threading.Thread(target=_worker, daemon=True)
    thread.start()
    return thread


def _k8s_create_job(
    name: str,
    image: str,  # noqa: ARG001
    experiment_id: str,
    command: str,
    resources: dict | None = None,  # noqa: ARG001
) -> None:
    # Extract the mwf analysis name from the "-i <name>" flag at the end of the command
    match = re.search(r"-i\s+(\w+)\s*$", command)
    analysis_name = match.group(1) if match else ""
    demo_state.analysis_jobs[name] = {
        "status": JobStatus.RUNNING.value,
        "experiment_id": experiment_id,
        "analysis_name": analysis_name,
        "created_at": time.time(),
    }
    thread = threading.Thread(
        target=_fetch_and_store_analysis,
        args=(name, experiment_id, analysis_name),
        daemon=True,
    )
    thread.start()


def _k8s_get_job_status(name: str) -> JobStatus:
    job_data = demo_state.analysis_jobs.get(name)
    if job_data is None:
        return JobStatus.UNKNOWN
    try:
        return JobStatus(job_data.get("status", JobStatus.UNKNOWN.value))
    except ValueError:
        return JobStatus.UNKNOWN


def _k8s_delete_job(name: str) -> None:
    demo_state.analysis_jobs.pop(name, None)


def _k8s_get_job_logs(name: str, tail_lines: int = 200) -> str:  # noqa: ARG001
    job_data = demo_state.analysis_jobs.get(name)
    if job_data is None:
        logger.warning("get_job_logs: job '%s' not in demo_state (keys: %s)", name, list(demo_state.analysis_jobs))
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
    """GET a MDposit analysis endpoint, following redirects with JSON acceptance."""
    headers = {"Accept": "application/json"}
    return _real_requests_get(f"{MDPOSIT_ANALYSES_URL}/{path}", headers=headers, timeout=30)


def _fetch_and_store_analysis(job_name: str, experiment_id: str, analysis_name: str) -> None:
    """Fetch analysis data from MDposit and write result files, then mark the job done."""
    time.sleep(ANALYSIS_JOB_DURATION_SEC)
    try:
        mdposit_name = _MDPOSIT_NAME_MAP.get(analysis_name, analysis_name)
        response = _mdposit_get(mdposit_name)
        if not response.ok:
            logger.warning(
                f"MDposit returned {response.status_code} for analysis '{analysis_name}' (endpoint: '{mdposit_name}')"
            )
            demo_state.analysis_jobs[job_name]["status"] = JobStatus.ERROR.value
            return

        data = response.json()
        mwf_dir = DATA_DIR / experiment_id / MWF_DIR
        mwf_dir.mkdir(parents=True, exist_ok=True)

        # Use the mwf output name (= MDposit endpoint name), not the AnalysisType value.
        # mwf uses different output file names for some analyses (e.g. "-i inter" produces
        # mda.interactions.json, "-i rmsf" produces mda.fluctuation.json). This matches
        # the frontend's resultName values and what find_result_file() looks for.
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
    except Exception:
        logger.exception(f"Failed to fetch analysis '{analysis_name}' for demo job {job_name}")
        if job_name in demo_state.analysis_jobs:
            demo_state.analysis_jobs[job_name]["status"] = JobStatus.ERROR.value


def _advance_gmx_job(job_id: str, job_data: dict[str, Any]) -> None:
    if job_data.get("status") != JobStatus.RUNNING.value:
        return

    created_at = float(job_data.get("created_at", time.time()))
    duration_sec = float(job_data.get("duration_sec", DEFAULT_GMX_DURATION_SEC))
    elapsed = max(0.0, time.time() - created_at)
    experiment_id = str(job_data.get("experiment_id", ""))
    tpr_name = str(job_data.get("tpr_name", ""))
    nsteps = int(job_data.get("nsteps", DEFAULT_GMX_NSTEPS))
    if experiment_id and tpr_name and duration_sec > 0:
        progress_ratio = min(1.0, elapsed / duration_sec)
        log_total_lines = int(job_data.get("log_total_lines", gmx_log_template_line_count()))
        target_log_index = int(log_total_lines * progress_ratio)
        current_index = append_gmx_log_template_until(experiment_id, Path(tpr_name).stem, target_log_index)
        job_data["log_line_index"] = current_index

    if elapsed < duration_sec:
        return

    job_data["status"] = JobStatus.TERMINATED.value
    performance = 62.5
    if experiment_id and tpr_name:
        write_finished_gmx_log(
            experiment_id,
            Path(tpr_name).stem,
            nsteps=nsteps,
            performance=performance,
            append_only=True,
        )

    gmx_job = GromacsJob.query.filter_by(id=job_id).first()
    if gmx_job is None:
        return
    gmx_job._performance = performance  # noqa: SLF001
    gmx_job._finish_timestamp = int(time.time())  # noqa: SLF001
    db.session.commit()


def _advance_tuner_status(status: dict[str, Any]) -> None:
    if status.get("status") != JobStatus.RUNNING.value:
        return

    trials = status.get("trials")
    if not isinstance(trials, list):
        trials = []
        status["trials"] = trials
    running_trial = next((t for t in trials if t.get("status") == JobStatus.RUNNING.value), None)
    now = time.time()

    if running_trial is not None:
        started_at = float(running_trial.get("started_at", now))
        if now - started_at >= TUNER_TRIAL_DURATION_SEC:
            running_trial["status"] = JobStatus.TERMINATED.value
            running_trial["performance"] = 55.0 + len(trials)
        return

    max_trials = int(status.get("max_trials", DEFAULT_TUNER_MAX_TRIALS))
    if len(trials) >= max_trials:
        status["status"] = JobStatus.TERMINATED.value
        return

    next_id = f"trial-{len(trials):05d}"
    trials.append({
        "id": next_id,
        "status": JobStatus.RUNNING.value,
        "np": 2,
        "ntomp": 4,
        "nb": "cpu",
        "pme": "cpu",
        "performance": None,
        "started_at": now,
    })


def _public_trial(trial: dict[str, object]) -> dict[str, object]:
    public_trial = dict(trial)
    public_trial.pop("started_at", None)
    return public_trial
