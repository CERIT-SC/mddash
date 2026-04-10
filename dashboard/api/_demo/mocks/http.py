"""
HTTP mocking for external services using the responses library.

Intercepts all requests calls at the network level, providing realistic
responses based on actual API specifications.
"""

import json
import logging
import re
import time
from http import HTTPStatus
from typing import TYPE_CHECKING
from uuid import uuid4

import responses
from clients.caddy import CADDY_ADMIN_API_URL
from config import (
    DATA_DIR,
    MDREPO_API_URL,
    MDREPO_RECORD_NAME,
    MDREPO_TOKEN_URL,
    MDREPO_URL,
    MDRUN_API_URL,
    TUNER_URL,
)

from ..files import DEFAULT_PDB_FILE, build_demo_archive_bytes
from ..state import demo_state

if TYPE_CHECKING:
    from responses import ResponsesProxy

logger = logging.getLogger(__name__)

# Default simulation parameters
DEFAULT_GMX_NSTEPS = 100_000
DEFAULT_GMX_DURATION_SEC = 30.0
DEFAULT_TUNER_MAX_TRIALS = 3
TUNER_TRIAL_DURATION_SEC = 10.0


def install_http_mocks(rsps: responses.RequestsMock) -> None:
    """
    Install all HTTP response mocks.

    Args:
        rsps: The RequestsMock instance to register mocks on.
    """
    _install_mdrun_mocks(rsps)
    _install_tuner_mocks(rsps)
    _install_mdrepo_mocks(rsps)
    _install_caddy_mocks(rsps)
    _install_external_download_mocks(rsps)
    _install_mdposit_pass_through(rsps)


def _install_mdrun_mocks(rsps: responses.RequestsMock) -> None:
    """Install MDRun API response mocks."""

    def create_mdrun_job(request: "ResponsesProxy") -> tuple[int, dict[str, str], str]:
        """Create a new MDRun job."""
        try:
            body = json.loads(request.body or "{}")
        except json.JSONDecodeError:
            body = {}

        experiment_id = body.get("experiment_id", "unknown")
        tpr_name = body.get("tpr_name", "md.tpr")
        pme = body.get("pme", "cpu")
        nb = body.get("nb", "cpu")
        np_val = body.get("np", 2)
        ntomp = body.get("ntomp", 4)

        job_id = f"demo-gmx-{uuid4()}"
        started_at = time.time()

        demo_state.mdrun_jobs[job_id] = {
            "status": "RUNNING",
            "experiment_id": experiment_id,
            "tpr_name": tpr_name,
            "nsteps": DEFAULT_GMX_NSTEPS,
            "created_at": started_at,
            "duration_sec": DEFAULT_GMX_DURATION_SEC,
            "log_line_index": 0,
            "log_total_lines": 500,
        }

        response_body = {
            "success": True,
            "data": {
                "id": job_id,
                "status": "RUNNING",
                "bucket_name": body.get("bucket_name", "demo-bucket"),
                "pme": pme,
                "nb": nb,
                "np": np_val,
                "ntomp": ntomp,
                "extra_args": body.get("extra_args", ""),
            },
        }
        return (HTTPStatus.CREATED, {}, json.dumps(response_body))

    def get_mdrun_job(request: "ResponsesProxy") -> tuple[int, dict[str, str], str]:
        """Get MDRun job status."""
        match = re.search(rf"{re.escape(MDRUN_API_URL)}/jobs/(?P<job_id>[^/]+)", request.url)
        if not match:
            return (HTTPStatus.NOT_FOUND, {}, json.dumps({"success": False, "message": "Job not found"}))

        job_id = match.group("job_id")
        job_data = demo_state.mdrun_jobs.get(job_id)

        if job_data is None:
            return (HTTPStatus.NOT_FOUND, {}, json.dumps({"success": False, "message": f"Job {job_id} not found"}))

        _advance_mdrun_job(job_id, job_data)

        response_body = {
            "success": True,
            "data": {"id": job_id, "status": job_data["status"]},
        }
        return (HTTPStatus.OK, {}, json.dumps(response_body))

    def delete_mdrun_job(request: "ResponsesProxy") -> tuple[int, dict[str, str], str]:
        """Delete an MDRun job."""
        match = re.search(rf"{re.escape(MDRUN_API_URL)}/jobs/(?P<job_id>[^/]+)", request.url)
        if match:
            demo_state.mdrun_jobs.pop(match.group("job_id"), None)
        return (HTTPStatus.NO_CONTENT, {}, "")

    rsps.add_callback(responses.POST, f"{MDRUN_API_URL}/jobs", callback=create_mdrun_job)
    rsps.add_callback(responses.GET, re.compile(rf"{re.escape(MDRUN_API_URL)}/jobs/[^/]+"), callback=get_mdrun_job)
    rsps.add_callback(responses.DELETE, re.compile(rf"{re.escape(MDRUN_API_URL)}/jobs/[^/]+"), callback=delete_mdrun_job)


def _install_tuner_mocks(rsps: responses.RequestsMock) -> None:
    """Install GROMACS Tuner API response mocks."""

    def submit_tuner_job(request: "ResponsesProxy") -> tuple[int, dict[str, str], str]:
        """Submit a GROMACS tuning job."""
        job_id = f"demo-tuner-{uuid4()}"
        started_at = time.time()

        # Create initial trials with deterministic outcomes:
        # - Trial 0: TERMINATED successfully (good config)
        # - Trial 1: ERROR (failed execution)
        # - Trial 2: RUNNING (currently in progress)
        demo_state.tuner_jobs[job_id] = {
            "status": "RUNNING",
            "created_at": started_at,
            "max_trials": DEFAULT_TUNER_MAX_TRIALS,
            "trials": [
                {
                    "id": f"{job_id[:10]}-00000",
                    "status": "TERMINATED",
                    "np": 8,
                    "ntomp": 1,
                    "nb": "gpu",
                    "pme": "cpu",
                    "performance": 68.5,
                    "started_at": started_at - TUNER_TRIAL_DURATION_SEC * 2,
                },
                {
                    "id": f"{job_id[:10]}-00001",
                    "status": "ERROR",
                    "np": 4,
                    "ntomp": 2,
                    "nb": "cpu",
                    "pme": "cpu",
                    "performance": None,
                    "started_at": started_at - TUNER_TRIAL_DURATION_SEC,
                },
                {
                    "id": f"{job_id[:10]}-00002",
                    "status": "RUNNING",
                    "np": 4,
                    "ntomp": 2,
                    "nb": "gpu",
                    "pme": "gpu",
                    "performance": None,
                    "started_at": started_at,
                },
            ],
        }

        response_body = {"id": job_id, "status": "PENDING"}
        return (HTTPStatus.CREATED, {}, json.dumps(response_body))

    def get_tuner_status(request: "ResponsesProxy") -> tuple[int, dict[str, str], str]:
        """Get GROMACS tuning job status."""
        match = re.search(rf"{re.escape(TUNER_URL)}/tuning-jobs/gmx/(?P<job_id>[^/]+)/status", request.url)
        job_id = match.group("job_id") if match else ""
        job_state = demo_state.tuner_jobs.get(job_id)

        if job_state is None:
            return (HTTPStatus.OK, {}, json.dumps({"id": job_id, "status": "UNKNOWN", "trials": []}))

        _advance_tuner_status(job_state)

        public_trials = []
        for trial in job_state.get("trials", []):
            if isinstance(trial, dict):
                public_trials.append({
                    "id": trial.get("id", ""),
                    "status": trial.get("status", "UNKNOWN"),
                    "np": trial.get("np", 2),
                    "ntomp": trial.get("ntomp", 4),
                    "nb": trial.get("nb", "cpu"),
                    "pme": trial.get("pme", "cpu"),
                    "performance": trial.get("performance"),
                })

        response_body = {
            "id": job_id,
            "status": job_state.get("status", "UNKNOWN"),
            "error": None,
            "trials": public_trials,
        }
        return (HTTPStatus.OK, {}, json.dumps(response_body))

    def delete_tuner_job(request: "ResponsesProxy") -> tuple[int, dict[str, str], str]:
        """Delete a GROMACS tuning job."""
        match = re.search(rf"{re.escape(TUNER_URL)}/tuning-jobs/gmx/(?P<job_id>[^/]+)", request.url)
        if match:
            demo_state.tuner_jobs.pop(match.group("job_id"), None)
        return (HTTPStatus.NO_CONTENT, {}, "")

    rsps.add_callback(responses.POST, f"{TUNER_URL}/tuning-jobs/gmx", callback=submit_tuner_job)
    rsps.add_callback(responses.GET, re.compile(rf"{re.escape(TUNER_URL)}/tuning-jobs/gmx/[^/]+/status"), callback=get_tuner_status)
    rsps.add_callback(responses.DELETE, re.compile(rf"{re.escape(TUNER_URL)}/tuning-jobs/gmx/[^/]+"), callback=delete_tuner_job)


def _install_mdrepo_mocks(rsps: responses.RequestsMock) -> None:
    """Install MDRepo (InvenioRDM) API response mocks."""

    def create_mdrepo_experiment(request: "ResponsesProxy") -> tuple[int, dict[str, str], str]:
        """Create a draft record in MDRepo."""
        record_id = "8gahj-dh519"
        demo_state.mdrepo_counter += 1
        demo_state.mdrepo_records[record_id] = False

        response_body = {
            "id": record_id,
            "created": "2026-04-10T12:00:00.000000",
            "updated": "2026-04-10T12:00:00.000000",
            "links": {
                "self": f"{MDREPO_URL}/{MDREPO_RECORD_NAME}/{record_id}",
                "self_html": f"{MDREPO_URL}/{MDREPO_RECORD_NAME}/records/{record_id}",
                "edit_html": f"{MDREPO_URL}/{MDREPO_RECORD_NAME}/uploads/{record_id}",
            },
            "state": "draft",
        }
        return (HTTPStatus.CREATED, {}, json.dumps(response_body))

    def get_mdrepo_user(request: "ResponsesProxy") -> tuple[int, dict[str, str], str]:
        """Get current MDRepo user info."""
        auth_header = request.headers.get("Authorization", "")
        if auth_header.startswith("Bearer demo"):
            return (HTTPStatus.OK, {}, json.dumps({"user": "demo"}))
        return (HTTPStatus.UNAUTHORIZED, {}, json.dumps({"message": "Unauthorized"}))

    def get_mdrepo_published_record(request: "ResponsesProxy") -> tuple[int, dict[str, str], str]:
        """Check if record is published."""
        match = re.search(rf"{re.escape(MDREPO_API_URL)}/{re.escape(MDREPO_RECORD_NAME)}/(?P<record_id>[^/]+)$", request.url)
        if not match:
            return (HTTPStatus.NOT_FOUND, {}, json.dumps({"message": "Not found"}))

        record_id = match.group("record_id")
        if demo_state.mdrepo_records.get(record_id):
            return (HTTPStatus.OK, {}, json.dumps({"id": record_id, "state": "published"}))
        return (HTTPStatus.NOT_FOUND, {}, json.dumps({"message": "Not found"}))

    def get_mdrepo_draft_record(request: "ResponsesProxy") -> tuple[int, dict[str, str], str]:
        """Check if record exists as draft."""
        match = re.search(rf"{re.escape(MDREPO_API_URL)}/{re.escape(MDREPO_RECORD_NAME)}/(?P<record_id>[^/]+)/draft", request.url)
        if not match:
            return (HTTPStatus.NOT_FOUND, {}, json.dumps({"message": "Not found"}))

        record_id = match.group("record_id")
        if record_id in demo_state.mdrepo_records and demo_state.mdrepo_records[record_id] is False:
            return (HTTPStatus.OK, {}, json.dumps({"id": record_id, "state": "draft"}))
        return (HTTPStatus.NOT_FOUND, {}, json.dumps({"message": "Not found"}))

    def mdrepo_token_exchange(request: "ResponsesProxy") -> tuple[int, dict[str, str], str]:
        """Exchange OAuth code for token."""
        response_body = {
            "access_token": "demo-access-token",
            "refresh_token": "demo-refresh-token",
            "expires_in": 3600,
            "token_type": "Bearer",
        }
        return (HTTPStatus.OK, {}, json.dumps(response_body))

    rsps.add_callback(responses.POST, f"{MDREPO_API_URL}/{MDREPO_RECORD_NAME}", callback=create_mdrepo_experiment)
    rsps.add_callback(responses.GET, f"{MDREPO_URL}/api/me", callback=get_mdrepo_user)
    rsps.add_callback(responses.GET, re.compile(rf"{re.escape(MDREPO_API_URL)}/{re.escape(MDREPO_RECORD_NAME)}/[^/]+$"), callback=get_mdrepo_published_record)
    rsps.add_callback(responses.GET, re.compile(rf"{re.escape(MDREPO_API_URL)}/{re.escape(MDREPO_RECORD_NAME)}/[^/]+/draft"), callback=get_mdrepo_draft_record)
    if MDREPO_TOKEN_URL:
        rsps.add_callback(responses.POST, MDREPO_TOKEN_URL, callback=mdrepo_token_exchange)


def _install_caddy_mocks(rsps: responses.RequestsMock) -> None:
    """Install Caddy admin API response mocks."""

    def get_caddy_config(request: "ResponsesProxy") -> tuple[int, dict[str, str], str]:
        """Get current Caddy configuration."""
        response_body = {
            "apps": {
                "http": {
                    "servers": {
                        "srv0": {
                            "routes": [
                                {"@id": "route-1"},
                                {"@id": "route-2"},
                                {"match": [{"path_regexp": {"name": "dash_routes"}}]},
                            ]
                        }
                    }
                }
            }
        }
        return (HTTPStatus.OK, {}, json.dumps(response_body))

    def update_caddy_config(request: "ResponsesProxy") -> tuple[int, dict[str, str], str]:
        """Update Caddy configuration."""
        return (HTTPStatus.OK, {}, "")

    def delete_caddy_route(request: "ResponsesProxy") -> tuple[int, dict[str, str], str]:
        """Delete a Caddy route."""
        return (HTTPStatus.OK, {}, "")

    rsps.add_callback(responses.GET, f"{CADDY_ADMIN_API_URL}/config/", callback=get_caddy_config)
    rsps.add_callback(responses.POST, f"{CADDY_ADMIN_API_URL}/load", callback=update_caddy_config)
    rsps.add_callback(responses.DELETE, re.compile(rf"{re.escape(CADDY_ADMIN_API_URL)}/id/[a-zA-Z0-9_-]+"), callback=delete_caddy_route)


def _install_external_download_mocks(rsps: responses.RequestsMock) -> None:
    """Install mocks for external file downloads (PDB, Zenodo)."""

    def download_pdb_file(request: "ResponsesProxy") -> tuple[int, dict[str, str], bytes]:
        """Download a PDB file from RCSB."""
        if DEFAULT_PDB_FILE.exists():
            return (HTTPStatus.OK, {}, DEFAULT_PDB_FILE.read_bytes())
        return (HTTPStatus.NOT_FOUND, {}, b"")

    def download_zenodo_archive(request: "ResponsesProxy") -> tuple[int, dict[str, str], bytes]:
        """Download a Zenodo files archive."""
        return (HTTPStatus.OK, {}, build_demo_archive_bytes())

    def head_request(request: "ResponsesProxy") -> tuple[int, dict[str, str], str]:
        """Handle HEAD requests for URL validation."""
        return (HTTPStatus.OK, {}, "")

    rsps.add_callback(responses.GET, re.compile(r"https://files\.rcsb\.org/download/[A-Za-z0-9]+\.pdb"), callback=download_pdb_file)
    rsps.add_callback(responses.GET, re.compile(r"https://zenodo\.org/api/records/[0-9]+/files-archive"), callback=download_zenodo_archive)
    rsps.add_callback(responses.HEAD, re.compile(r"https://.*"), callback=head_request)


def _install_mdposit_pass_through(rsps: responses.RequestsMock) -> None:
    """Allow MDposit API requests to pass through (real network calls for analysis data)."""
    # Use passthrough for MDposit and its redirect targets so real requests are made
    rsps.add_passthru(re.compile(r"https://mdposit\.mddbr\.eu/.*"))
    rsps.add_passthru(re.compile(r"https://irb-dev\.mddbr\.eu/.*"))


def _advance_mdrun_job(job_id: str, job_data: dict) -> None:
    """Advance MDRun job state based on elapsed time."""
    if job_data.get("status") != "RUNNING":
        return

    created_at = float(job_data.get("created_at", time.time()))
    duration_sec = float(job_data.get("duration_sec", DEFAULT_GMX_DURATION_SEC))
    elapsed = max(0.0, time.time() - created_at)

    log_total_lines = int(job_data.get("log_total_lines", 500))
    progress_ratio = min(1.0, elapsed / duration_sec) if duration_sec > 0 else 1.0
    job_data["log_line_index"] = int(log_total_lines * progress_ratio)

    if elapsed >= duration_sec:
        job_data["status"] = "TERMINATED"
        job_data["performance"] = 62.5

        try:
            from extensions import db
            from models import GromacsJob

            gmx_job = GromacsJob.query.filter_by(id=job_id).first()
            if gmx_job is not None:
                gmx_job._performance = 62.5  # noqa: SLF001
                gmx_job._finish_timestamp = int(time.time())  # noqa: SLF001
                db.session.commit()
        except Exception:
            pass


def _advance_tuner_status(status: dict) -> None:
    """Advance tuner job state based on elapsed time.

    Deterministic pattern: even-indexed trials TERMINATE, odd-indexed trials ERROR.
    This creates a predictable mix of successful and failed runs.
    """
    if status.get("status") != "RUNNING":
        return

    trials = status.get("trials")
    if not isinstance(trials, list):
        trials = []
        status["trials"] = trials

    running_trial = next((t for t in trials if t.get("status") == "RUNNING"), None)
    now = time.time()

    if running_trial is not None:
        started_at = float(running_trial.get("started_at", now))
        if now - started_at >= TUNER_TRIAL_DURATION_SEC:
            trial_idx = trials.index(running_trial)
            # Deterministic: even indices TERMINATE, odd indices ERROR
            if trial_idx % 2 == 0:
                running_trial["status"] = "TERMINATED"
                base_perf = 55.0
                np = running_trial.get("np", 2)
                nb = running_trial.get("nb", "cpu")
                if nb == "gpu":
                    base_perf += 15.0
                running_trial["performance"] = base_perf + (np * 2.5) + trial_idx
            else:
                running_trial["status"] = "ERROR"
                running_trial["performance"] = None
        return

    max_trials = int(status.get("max_trials", DEFAULT_TUNER_MAX_TRIALS))
    if len(trials) >= max_trials:
        status["status"] = "TERMINATED"
        return

    # Generate varied configurations for new trials
    trial_configs = [
        {"np": 8, "ntomp": 1, "nb": "cpu", "pme": "cpu"},
        {"np": 4, "ntomp": 2, "nb": "cpu", "pme": "cpu"},
        {"np": 2, "ntomp": 4, "nb": "cpu", "pme": "cpu"},
        {"np": 8, "ntomp": 1, "nb": "gpu", "pme": "cpu"},
        {"np": 4, "ntomp": 2, "nb": "gpu", "pme": "gpu"},
        {"np": 2, "ntomp": 4, "nb": "gpu", "pme": "gpu"},
    ]
    config_idx = len(trials) % len(trial_configs)
    config = trial_configs[config_idx]

    trials.append({
        "id": f"trial-{len(trials):05d}",
        "status": "RUNNING",
        **config,
        "performance": None,
        "started_at": now,
    })