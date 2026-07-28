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
from urllib.parse import unquote
from uuid import uuid4

import responses
from clients.caddy import CADDY_ADMIN_API_URL
from config import (
    MDPOSIT_REST_URL,
    MDREPO_API_URL,
    MDREPO_RECORD_NAME,
    MDREPO_TOKEN_URL,
    MDREPO_URL,
    MDRUN_API_URL,
    METADUMP_API_URL,
    TUNER_URL,
)

from ..files import DEFAULT_PDB_FILE, build_demo_archive_bytes, get_mdposit_fixture_bytes
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
    _install_mdposit_mocks(rsps)
    _install_metadump_mocks(rsps)
    _install_caddy_mocks(rsps)
    _install_external_download_mocks(rsps)


def _install_mdrun_mocks(rsps: responses.RequestsMock) -> None:
    """Install MDRun API response mocks."""

    def create_gmx_job(request: "ResponsesProxy") -> tuple[int, dict[str, str], str]:
        """
        Create a new GROMACS MDRun job.

        Returns:
            Tuple of (status_code, headers, body) for the response.
        """
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
            "id": job_id,
            "status": "RUNNING",
            "bucket_name": body.get("bucket_name", "demo-bucket"),
            "pme": pme,
            "nb": nb,
            "np": np_val,
            "ntomp": ntomp,
            "extra_args": body.get("extra_args", ""),
        }
        return (HTTPStatus.CREATED, {}, json.dumps(response_body))

    def create_amber_job(request: "ResponsesProxy") -> tuple[int, dict[str, str], str]:
        """
        Create a new AMBER MDRun job.

        Returns:
            Tuple of (status_code, headers, body) for the response.
        """
        try:
            body = json.loads(request.body or "{}")
        except json.JSONDecodeError:
            body = {}

        experiment_id = body.get("experiment_id", "unknown")
        prmtop_name = body.get("prmtop_name", "md.prmtop")
        inpcrd_name = body.get("inpcrd_name", "md.inpcrd")
        mdin_name = body.get("mdin_name", "md.mdin")
        binary = body.get("binary", "pmemd.MPI")
        ewald = body.get("ewald", "default")
        np_val = body.get("np", 2)
        ntomp = body.get("ntomp", 4)

        job_id = f"demo-amber-{uuid4()}"
        started_at = time.time()

        demo_state.mdrun_jobs[job_id] = {
            "status": "RUNNING",
            "experiment_id": experiment_id,
            "prmtop_name": prmtop_name,
            "inpcrd_name": inpcrd_name,
            "mdin_name": mdin_name,
            "nsteps": DEFAULT_GMX_NSTEPS,
            "created_at": started_at,
            "duration_sec": DEFAULT_GMX_DURATION_SEC,
            "log_line_index": 0,
            "log_total_lines": 500,
        }

        response_body = {
            "id": job_id,
            "status": "RUNNING",
            "bucket_name": body.get("bucket_name", "demo-bucket"),
            "binary": binary,
            "ewald": ewald,
            "np": np_val,
            "ntomp": ntomp,
            "extra_args": body.get("extra_args", ""),
        }
        return (HTTPStatus.CREATED, {}, json.dumps(response_body))

    def get_gmx_job(request: "ResponsesProxy") -> tuple[int, dict[str, str], str]:
        """
        Get GROMACS job status.

        Returns:
            Tuple of (status_code, headers, body) for the response.
        """
        match = re.search(rf"{re.escape(MDRUN_API_URL)}/jobs/gmx/(?P<job_id>[^/]+)", request.url)
        if not match:
            return (
                HTTPStatus.NOT_FOUND,
                {},
                json.dumps({"type": "urn:mddash:not-found", "title": "Not Found", "detail": "Job not found"}),
            )

        job_id = match.group("job_id")
        job_data = demo_state.mdrun_jobs.get(job_id)

        if job_data is None:
            return (
                HTTPStatus.NOT_FOUND,
                {},
                json.dumps({"type": "urn:mddash:not-found", "title": "Not Found", "detail": f"Job {job_id} not found"}),
            )

        _advance_mdrun_job(job_id, job_data)

        response_body = {"id": job_id, "status": job_data["status"]}
        return (HTTPStatus.OK, {}, json.dumps(response_body))

    def get_amber_job(request: "ResponsesProxy") -> tuple[int, dict[str, str], str]:
        """
        Get AMBER job status.

        Returns:
            Tuple of (status_code, headers, body) for the response.
        """
        match = re.search(rf"{re.escape(MDRUN_API_URL)}/jobs/amber/(?P<job_id>[^/]+)", request.url)
        if not match:
            return (
                HTTPStatus.NOT_FOUND,
                {},
                json.dumps({"type": "urn:mddash:not-found", "title": "Not Found", "detail": "Job not found"}),
            )

        job_id = match.group("job_id")
        job_data = demo_state.mdrun_jobs.get(job_id)

        if job_data is None:
            return (
                HTTPStatus.NOT_FOUND,
                {},
                json.dumps({"type": "urn:mddash:not-found", "title": "Not Found", "detail": f"Job {job_id} not found"}),
            )

        _advance_mdrun_job(job_id, job_data)

        response_body = {"id": job_id, "status": job_data["status"]}
        return (HTTPStatus.OK, {}, json.dumps(response_body))

    def delete_gmx_job(request: "ResponsesProxy") -> tuple[int, dict[str, str], str]:
        """
        Delete a GROMACS job.

        Returns:
            Tuple of (status_code, headers, body) for the response.
        """
        match = re.search(rf"{re.escape(MDRUN_API_URL)}/jobs/gmx/(?P<job_id>[^/]+)", request.url)
        if match:
            demo_state.mdrun_jobs.pop(match.group("job_id"), None)
        return (HTTPStatus.NO_CONTENT, {}, "")

    def delete_amber_job(request: "ResponsesProxy") -> tuple[int, dict[str, str], str]:
        """
        Delete an AMBER job.

        Returns:
            Tuple of (status_code, headers, body) for the response.
        """
        match = re.search(rf"{re.escape(MDRUN_API_URL)}/jobs/amber/(?P<job_id>[^/]+)", request.url)
        if match:
            demo_state.mdrun_jobs.pop(match.group("job_id"), None)
        return (HTTPStatus.NO_CONTENT, {}, "")

    # Legacy endpoints (for backward compatibility)
    rsps.add_callback(responses.POST, f"{MDRUN_API_URL}/jobs", callback=create_gmx_job)
    rsps.add_callback(
        responses.GET, re.compile(rf"{re.escape(MDRUN_API_URL)}/jobs/(?!gmx|amber)[^/]+"), callback=get_gmx_job
    )
    rsps.add_callback(
        responses.DELETE, re.compile(rf"{re.escape(MDRUN_API_URL)}/jobs/(?!gmx|amber)[^/]+"), callback=delete_gmx_job
    )

    # GROMACS-specific endpoints
    rsps.add_callback(responses.POST, f"{MDRUN_API_URL}/jobs/gmx", callback=create_gmx_job)
    rsps.add_callback(responses.GET, re.compile(rf"{re.escape(MDRUN_API_URL)}/jobs/gmx/[^/]+"), callback=get_gmx_job)
    rsps.add_callback(
        responses.DELETE, re.compile(rf"{re.escape(MDRUN_API_URL)}/jobs/gmx/[^/]+"), callback=delete_gmx_job
    )

    # AMBER-specific endpoints
    rsps.add_callback(responses.POST, f"{MDRUN_API_URL}/jobs/amber", callback=create_amber_job)
    rsps.add_callback(
        responses.GET, re.compile(rf"{re.escape(MDRUN_API_URL)}/jobs/amber/[^/]+"), callback=get_amber_job
    )
    rsps.add_callback(
        responses.DELETE, re.compile(rf"{re.escape(MDRUN_API_URL)}/jobs/amber/[^/]+"), callback=delete_amber_job
    )


def _install_tuner_mocks(rsps: responses.RequestsMock) -> None:
    """Install Tuner API response mocks for GMX and AMBER engines."""

    def submit_gmx_tuner_job(_request: "ResponsesProxy") -> tuple[int, dict[str, str], str]:
        """
        Submit a GROMACS tuning job.

        Returns:
            Tuple of (status_code, headers, body) for the response.
        """
        job_id = f"demo-tuner-{uuid4()}"
        started_at = time.time()

        demo_state.tuner_jobs[job_id] = {
            "status": "RUNNING",
            "engine": "gmx",
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

    def submit_amber_tuner_job(_request: "ResponsesProxy") -> tuple[int, dict[str, str], str]:
        """
        Submit an AMBER tuning job.

        Returns:
            Tuple of (status_code, headers, body) for the response.
        """
        job_id = f"demo-amber-tuner-{uuid4()}"
        started_at = time.time()

        demo_state.tuner_jobs[job_id] = {
            "status": "RUNNING",
            "engine": "amber",
            "created_at": started_at,
            "max_trials": DEFAULT_TUNER_MAX_TRIALS,
            "trials": [
                {
                    "id": f"{job_id[:10]}-00000",
                    "status": "TERMINATED",
                    "np": 4,
                    "ntomp": 1,
                    "binary": "pmemd.cuda",
                    "ewald": "optimized",
                    "performance": 72.3,
                    "started_at": started_at - TUNER_TRIAL_DURATION_SEC * 2,
                },
                {
                    "id": f"{job_id[:10]}-00001",
                    "status": "ERROR",
                    "np": 1,
                    "ntomp": 4,
                    "binary": "pmemd.MPI",
                    "ewald": "default",
                    "performance": None,
                    "started_at": started_at - TUNER_TRIAL_DURATION_SEC,
                },
                {
                    "id": f"{job_id[:10]}-00002",
                    "status": "RUNNING",
                    "np": 4,
                    "ntomp": 1,
                    "binary": "pmemd.cuda",
                    "ewald": "default",
                    "performance": None,
                    "started_at": started_at,
                },
            ],
        }

        response_body = {"id": job_id, "status": "PENDING"}
        return (HTTPStatus.CREATED, {}, json.dumps(response_body))

    def get_gmx_tuner_status(request: "ResponsesProxy") -> tuple[int, dict[str, str], str]:
        """
        Get GROMACS tuning job status.

        Returns:
            Tuple of (status_code, headers, body) for the response.
        """
        match = re.search(rf"{re.escape(TUNER_URL)}/tuning-jobs/gmx/(?P<job_id>[^/]+)/status", request.url)
        job_id = match.group("job_id") if match else ""
        job_state = demo_state.tuner_jobs.get(job_id)

        if job_state is None:
            return (HTTPStatus.OK, {}, json.dumps({"id": job_id, "status": "UNKNOWN", "trials": []}))

        _advance_gmx_tuner_status(job_state)

        public_trials = [
            {
                "id": trial.get("id", ""),
                "status": trial.get("status", "UNKNOWN"),
                "np": trial.get("np", 2),
                "ntomp": trial.get("ntomp", 4),
                "nb": trial.get("nb", "cpu"),
                "pme": trial.get("pme", "cpu"),
                "performance": trial.get("performance"),
            }
            for trial in job_state.get("trials", [])
            if isinstance(trial, dict)
        ]

        response_body = {
            "id": job_id,
            "status": job_state.get("status", "UNKNOWN"),
            "error": None,
            "trials": public_trials,
        }
        return (HTTPStatus.OK, {}, json.dumps(response_body))

    def get_amber_tuner_status(request: "ResponsesProxy") -> tuple[int, dict[str, str], str]:
        """
        Get AMBER tuning job status.

        Returns:
            Tuple of (status_code, headers, body) for the response.
        """
        match = re.search(rf"{re.escape(TUNER_URL)}/tuning-jobs/amber/(?P<job_id>[^/]+)/status", request.url)
        job_id = match.group("job_id") if match else ""
        job_state = demo_state.tuner_jobs.get(job_id)

        if job_state is None:
            return (HTTPStatus.OK, {}, json.dumps({"id": job_id, "status": "UNKNOWN", "trials": []}))

        _advance_amber_tuner_status(job_state)

        public_trials = [
            {
                "id": trial.get("id", ""),
                "status": trial.get("status", "UNKNOWN"),
                "np": trial.get("np", 1),
                "ntomp": trial.get("ntomp", 1),
                "binary": trial.get("binary", "pmemd.MPI"),
                "ewald": trial.get("ewald", "default"),
                "performance": trial.get("performance"),
            }
            for trial in job_state.get("trials", [])
            if isinstance(trial, dict)
        ]

        response_body = {
            "id": job_id,
            "status": job_state.get("status", "UNKNOWN"),
            "error": None,
            "trials": public_trials,
        }
        return (HTTPStatus.OK, {}, json.dumps(response_body))

    def delete_gmx_tuner_job(request: "ResponsesProxy") -> tuple[int, dict[str, str], str]:
        """
        Delete a GROMACS tuning job.

        Returns:
            Tuple of (status_code, headers, body) for the response.
        """
        match = re.search(rf"{re.escape(TUNER_URL)}/tuning-jobs/gmx/(?P<job_id>[^/]+)", request.url)
        if match:
            demo_state.tuner_jobs.pop(match.group("job_id"), None)
        return (HTTPStatus.NO_CONTENT, {}, "")

    def delete_amber_tuner_job(request: "ResponsesProxy") -> tuple[int, dict[str, str], str]:
        """
        Delete an AMBER tuning job.

        Returns:
            Tuple of (status_code, headers, body) for the response.
        """
        match = re.search(rf"{re.escape(TUNER_URL)}/tuning-jobs/amber/(?P<job_id>[^/]+)", request.url)
        if match:
            demo_state.tuner_jobs.pop(match.group("job_id"), None)
        return (HTTPStatus.NO_CONTENT, {}, "")

    rsps.add_callback(responses.POST, f"{TUNER_URL}/tuning-jobs/gmx", callback=submit_gmx_tuner_job)
    rsps.add_callback(
        responses.GET,
        re.compile(rf"{re.escape(TUNER_URL)}/tuning-jobs/gmx/[^/]+/status"),
        callback=get_gmx_tuner_status,
    )
    rsps.add_callback(
        responses.DELETE, re.compile(rf"{re.escape(TUNER_URL)}/tuning-jobs/gmx/[^/]+"), callback=delete_gmx_tuner_job
    )
    rsps.add_callback(responses.POST, f"{TUNER_URL}/tuning-jobs/amber", callback=submit_amber_tuner_job)
    rsps.add_callback(
        responses.GET,
        re.compile(rf"{re.escape(TUNER_URL)}/tuning-jobs/amber/[^/]+/status"),
        callback=get_amber_tuner_status,
    )
    rsps.add_callback(
        responses.DELETE,
        re.compile(rf"{re.escape(TUNER_URL)}/tuning-jobs/amber/[^/]+"),
        callback=delete_amber_tuner_job,
    )


def _install_mdrepo_mocks(rsps: responses.RequestsMock) -> None:
    """Install MDRepo (InvenioRDM) API response mocks."""

    def create_mdrepo_experiment(_request: "ResponsesProxy") -> tuple[int, dict[str, str], str]:
        """
        Create a draft record in MDRepo.

        Returns:
            Tuple of (status_code, headers, body) for the response.
        """
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
        """
        Get current MDRepo user info.

        Returns:
            Tuple of (status_code, headers, body) for the response.
        """
        auth_header = request.headers.get("Authorization", "")
        if auth_header.startswith("Bearer demo"):
            return (HTTPStatus.OK, {}, json.dumps({"user": "demo"}))
        return (HTTPStatus.UNAUTHORIZED, {}, json.dumps({"message": "Unauthorized"}))

    def get_mdrepo_published_record(request: "ResponsesProxy") -> tuple[int, dict[str, str], str]:
        """
        Check if record is published.

        Returns:
            Tuple of (status_code, headers, body) for the response.
        """
        match = re.search(
            rf"{re.escape(MDREPO_API_URL)}/{re.escape(MDREPO_RECORD_NAME)}/(?P<record_id>[^/]+)$", request.url
        )
        if not match:
            return (HTTPStatus.NOT_FOUND, {}, json.dumps({"message": "Not found"}))

        record_id = match.group("record_id")
        if demo_state.mdrepo_records.get(record_id):
            return (HTTPStatus.OK, {}, json.dumps({"id": record_id, "state": "published"}))
        return (HTTPStatus.NOT_FOUND, {}, json.dumps({"message": "Not found"}))

    def get_mdrepo_draft_record(request: "ResponsesProxy") -> tuple[int, dict[str, str], str]:
        """
        Check if record exists as draft.

        Returns:
            Tuple of (status_code, headers, body) for the response.
        """
        match = re.search(
            rf"{re.escape(MDREPO_API_URL)}/{re.escape(MDREPO_RECORD_NAME)}/(?P<record_id>[^/]+)/draft", request.url
        )
        if not match:
            return (HTTPStatus.NOT_FOUND, {}, json.dumps({"message": "Not found"}))

        record_id = match.group("record_id")
        if record_id in demo_state.mdrepo_records and demo_state.mdrepo_records[record_id] is False:
            return (HTTPStatus.OK, {}, json.dumps({"id": record_id, "state": "draft"}))
        return (HTTPStatus.NOT_FOUND, {}, json.dumps({"message": "Not found"}))

    def mdrepo_token_exchange(_request: "ResponsesProxy") -> tuple[int, dict[str, str], str]:
        """
        Exchange OAuth code for token.

        Returns:
            Tuple of (status_code, headers, body) for the response.
        """
        response_body = {
            "access_token": "demo-access-token",
            "refresh_token": "demo-refresh-token",
            "expires_in": 3600,
            "token_type": "Bearer",
        }
        return (HTTPStatus.OK, {}, json.dumps(response_body))

    rsps.add_callback(responses.POST, f"{MDREPO_API_URL}/{MDREPO_RECORD_NAME}", callback=create_mdrepo_experiment)
    rsps.add_callback(responses.GET, f"{MDREPO_URL}/api/me", callback=get_mdrepo_user)
    rsps.add_callback(
        responses.GET,
        re.compile(rf"{re.escape(MDREPO_API_URL)}/{re.escape(MDREPO_RECORD_NAME)}/[^/]+$"),
        callback=get_mdrepo_published_record,
    )
    rsps.add_callback(
        responses.GET,
        re.compile(rf"{re.escape(MDREPO_API_URL)}/{re.escape(MDREPO_RECORD_NAME)}/[^/]+/draft"),
        callback=get_mdrepo_draft_record,
    )
    if MDREPO_TOKEN_URL:
        rsps.add_callback(responses.POST, MDREPO_TOKEN_URL, callback=mdrepo_token_exchange)


def _install_metadump_mocks(rsps: responses.RequestsMock) -> None:
    """Install MetaDump API response mocks."""

    def annotate_tpr(_request: "ResponsesProxy") -> tuple[int, dict[str, str], str]:
        job_uuid = str(uuid4())
        response_body = {
            "uuid": job_uuid,
            "pin": "123456",
            "status_url": f"{METADUMP_API_URL}/api/annotate/{job_uuid}",
            "results_url": f"{METADUMP_API_URL}/api/annotate/{job_uuid}/results",
        }
        return (HTTPStatus.CREATED, {}, json.dumps(response_body))

    def get_annotate_status(request: "ResponsesProxy") -> tuple[int, dict[str, str], str]:
        match = re.search(r"/api/annotate/(?P<uuid>[^/]+)$", request.url)
        job_uuid = match.group("uuid") if match else "unknown"
        response_body = {
            "uuid": job_uuid,
            "status": "completed",
            "created": "2026-05-02T12:00:00.000000",
            "options": {"keep": False},
        }
        return (HTTPStatus.OK, {}, json.dumps(response_body))

    def get_annotate_results(request: "ResponsesProxy") -> tuple[int, dict[str, str], str]:
        match = re.search(r"/api/annotate/(?P<uuid>[^/]+)/results", request.url)
        job_uuid = match.group("uuid") if match else "unknown"
        response_body = {
            "uuid": job_uuid,
            "metadata": {
                "forcefield": "charmm36",
                "water_model": "tip3p",
                "nsteps": 100000,
                "dt": 0.002,
            },
        }
        return (HTTPStatus.OK, {}, json.dumps(response_body))

    def delete_annotate_job(request: "ResponsesProxy") -> tuple[int, dict[str, str], str]:
        match = re.search(r"/api/annotate/(?P<uuid>[^/]+)", request.url)
        job_uuid = match.group("uuid") if match else "unknown"
        return (HTTPStatus.OK, {}, json.dumps({"message": f"Job {job_uuid} deleted"}))

    if METADUMP_API_URL:
        rsps.add_callback(responses.POST, f"{METADUMP_API_URL}/api/annotate", callback=annotate_tpr)
        # /results must be registered before the status route — responses matches in registration order
        rsps.add_callback(
            responses.GET,
            re.compile(rf"{re.escape(METADUMP_API_URL)}/api/annotate/[^/]+/results"),
            callback=get_annotate_results,
        )
        rsps.add_callback(
            responses.GET,
            re.compile(rf"{re.escape(METADUMP_API_URL)}/api/annotate/[^/]+$"),
            callback=get_annotate_status,
        )
        rsps.add_callback(
            responses.DELETE,
            re.compile(rf"{re.escape(METADUMP_API_URL)}/api/annotate/[^/]+"),
            callback=delete_annotate_job,
        )


def _install_caddy_mocks(rsps: responses.RequestsMock) -> None:
    """Install Caddy admin API response mocks."""

    def get_caddy_config(_request: "ResponsesProxy") -> tuple[int, dict[str, str], str]:
        """
        Get current Caddy configuration.

        Returns:
            Tuple of (status_code, headers, body) for the response.
        """
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

    def update_caddy_config(_request: "ResponsesProxy") -> tuple[int, dict[str, str], str]:
        """
        Update Caddy configuration.

        Returns:
            Tuple of (status_code, headers, body) for the response.
        """
        return (HTTPStatus.OK, {}, "")

    def delete_caddy_route(_request: "ResponsesProxy") -> tuple[int, dict[str, str], str]:
        """
        Delete a Caddy route.

        Returns:
            Tuple of (status_code, headers, body) for the response.
        """
        return (HTTPStatus.OK, {}, "")

    rsps.add_callback(responses.GET, f"{CADDY_ADMIN_API_URL}/config/", callback=get_caddy_config)
    rsps.add_callback(responses.POST, f"{CADDY_ADMIN_API_URL}/load", callback=update_caddy_config)
    rsps.add_callback(
        responses.DELETE,
        re.compile(rf"{re.escape(CADDY_ADMIN_API_URL)}/id/[a-zA-Z0-9_-]+"),
        callback=delete_caddy_route,
    )


def _install_external_download_mocks(rsps: responses.RequestsMock) -> None:
    """Install mocks for external file downloads (PDB, Zenodo)."""

    def download_pdb_file(_request: "ResponsesProxy") -> tuple[int, dict[str, str], bytes]:
        """
        Download a PDB file from RCSB.

        Returns:
            Tuple of (status_code, headers, body) for the response.
        """
        if DEFAULT_PDB_FILE.exists():
            return (HTTPStatus.OK, {}, DEFAULT_PDB_FILE.read_bytes())
        return (HTTPStatus.NOT_FOUND, {}, b"")

    def download_zenodo_archive(_request: "ResponsesProxy") -> tuple[int, dict[str, str], bytes]:
        """
        Download a Zenodo files archive.

        Returns:
            Tuple of (status_code, headers, body) for the response.
        """
        return (HTTPStatus.OK, {}, build_demo_archive_bytes())

    def head_request(_request: "ResponsesProxy") -> tuple[int, dict[str, str], str]:
        """
        Handle HEAD requests for URL validation.

        Returns:
            Tuple of (status_code, headers, body) for the response.
        """
        return (HTTPStatus.OK, {}, "")

    rsps.add_callback(
        responses.GET, re.compile(r"https://files\.rcsb\.org/download/[A-Za-z0-9]+\.pdb"), callback=download_pdb_file
    )
    rsps.add_callback(
        responses.GET,
        re.compile(r"https://zenodo\.org/api/records/[0-9]+/files-archive"),
        callback=download_zenodo_archive,
    )
    rsps.add_callback(responses.HEAD, re.compile(r"https://.*"), callback=head_request)


ANALYSIS_FIXTURES: dict[str, object] = {
    "rmsds": {
        "start": 0,
        "step": 100,
        "data": [
            {
                "reference": "backbone",
                "group": "C-alpha",
                "values": [0.0, 0.12, 0.23, 0.31, 0.38, 0.42, 0.45, 0.47, 0.49, 0.50],
            },
            {
                "reference": "backbone",
                "group": "Mainchain",
                "values": [0.0, 0.11, 0.21, 0.29, 0.35, 0.39, 0.42, 0.44, 0.46, 0.47],
            },
        ],
    },
    "sasa": {
        "saspf": [
            [120.5, 118.2, 115.8, 113.4, 111.0, 108.6, 106.2, 103.8, 101.4, 99.0],
            [85.3, 84.1, 82.9, 81.7, 80.5, 79.3, 78.1, 76.9, 75.7, 74.5],
            [210.4, 207.8, 205.2, 202.6, 200.0, 197.4, 194.8, 192.2, 189.6, 187.0],
            [65.1, 64.3, 63.5, 62.7, 61.9, 61.1, 60.3, 59.5, 58.7, 57.9],
            [150.2, 148.5, 146.8, 145.1, 143.4, 141.7, 140.0, 138.3, 136.6, 134.9],
        ],
        "means": [116.8, 79.9, 198.7, 61.1, 142.6],
        "stdvs": [7.5, 4.1, 8.9, 2.7, 5.9],
    },
    "hbonds": [
        {"name": "Protein-Water", "analysis": "hbonds-00"},
        {"name": "Intra-Protein", "analysis": "hbonds-01"},
    ],
    "hbonds-00": {
        "data": [
            {
                "name": "Protein-Water",
                "acceptors": [15, 27, 42, 58],
                "donors": [3, 19, 35, 51],
                "hydrogens": [8, 22, 38, 54],
                "hbonds": [
                    [True, False, True, True],
                    [False, True, False, True],
                    [True, True, True, False],
                    [False, False, True, True],
                    [True, True, False, False],
                ],
            }
        ]
    },
    "hbonds-01": {
        "data": [
            {
                "name": "Intra-Protein",
                "acceptors": [5, 12, 30],
                "donors": [8, 25, 45],
                "hydrogens": [7, 20, 40],
                "hbonds": [
                    [True, True, False],
                    [False, True, True],
                    [True, False, True],
                    [True, True, True],
                    [False, True, False],
                ],
            }
        ]
    },
}


def _install_mdposit_mocks(rsps: responses.RequestsMock) -> None:
    """Install deterministic MDPosit mocks for offline demo imports and analyses."""

    def get_project(request: "ResponsesProxy") -> tuple[int, dict[str, str], str]:
        accession = _extract_mdposit_accession(request.url)
        project = demo_state.mdposit_projects.get(accession)
        if project is None:
            return (
                HTTPStatus.NOT_FOUND,
                {},
                json.dumps({"type": "urn:mddash:not-found", "title": "Not Found", "detail": "Project not found"}),
            )
        response_body = {key: value for key, value in project.items() if key != "files"}
        return (HTTPStatus.OK, {"Content-Type": "application/json"}, json.dumps(response_body))

    def list_project_files(request: "ResponsesProxy") -> tuple[int, dict[str, str], str]:
        accession = _extract_mdposit_accession(request.url)
        project = demo_state.mdposit_projects.get(accession)
        if project is None:
            return (
                HTTPStatus.NOT_FOUND,
                {},
                json.dumps({"type": "urn:mddash:not-found", "title": "Not Found", "detail": "Project not found"}),
            )
        response_body = [{"name": filename} for filename in project.get("files", [])]
        return (HTTPStatus.OK, {"Content-Type": "application/json"}, json.dumps(response_body))

    def download_project_file(request: "ResponsesProxy") -> tuple[int, dict[str, str], bytes]:
        match = re.search(r"/api/projects/[^/]+/files/(?P<filename>.+)$", request.url)
        if not match:
            return (HTTPStatus.NOT_FOUND, {}, b"")

        accession = _extract_mdposit_accession(request.url)
        project = demo_state.mdposit_projects.get(accession)
        filename = unquote(match.group("filename"))
        if project is None or filename not in project.get("files", []):
            return (HTTPStatus.NOT_FOUND, {}, b"")

        content = get_mdposit_fixture_bytes(filename)
        if content is None:
            return (HTTPStatus.NOT_FOUND, {}, b"")
        return (HTTPStatus.OK, {"Content-Type": "application/octet-stream"}, content)

    def get_analysis(request: "ResponsesProxy") -> tuple[int, dict[str, str], str]:
        match = re.search(r"/analyses/(?P<analysis>[^/?#]+)", request.url)
        analysis_name = unquote(match.group("analysis")) if match else ""
        fixture = ANALYSIS_FIXTURES.get(analysis_name)
        if fixture is None:
            return (
                HTTPStatus.NOT_FOUND,
                {},
                json.dumps({
                    "type": "urn:mddash:not-found",
                    "title": "Not Found",
                    "detail": f"Analysis '{analysis_name}' not found",
                }),
            )
        return (HTTPStatus.OK, {"Content-Type": "application/json"}, json.dumps(fixture))

    project_base_pattern = _mdposit_project_base_pattern()
    rsps.add_callback(
        responses.GET,
        re.compile(rf"{project_base_pattern}/(?P<accession>[^/]+)/files/(?P<filename>.+)$"),
        callback=download_project_file,
    )
    rsps.add_callback(
        responses.GET,
        re.compile(rf"{project_base_pattern}/(?P<accession>[^/]+)/files$"),
        callback=list_project_files,
    )
    rsps.add_callback(
        responses.GET,
        re.compile(rf"{project_base_pattern}/(?P<accession>[^/]+)$"),
        callback=get_project,
    )
    rsps.add_callback(
        responses.GET,
        re.compile(_mdposit_analysis_pattern()),
        callback=get_analysis,
    )


def _mdposit_analysis_pattern() -> str:
    if MDPOSIT_REST_URL:
        base = re.escape(MDPOSIT_REST_URL.rstrip("/"))
        return rf"{base}/projects/[^/]+/analyses/[^/?#]+"
    return r"https://mdposit\.mddbr\.eu/api/rest/v1/projects/[^/]+/analyses/[^/?#]+"


def _mdposit_project_base_pattern() -> str:
    if MDPOSIT_REST_URL:
        return rf"{re.escape(MDPOSIT_REST_URL.rstrip('/'))}/projects"
    return r"https://mdposit\.mddbr\.eu/api/rest/v1/projects"


def _extract_mdposit_accession(url: str) -> str:
    match = re.search(r"/projects/(?P<accession>[^/]+)", url)
    return unquote(match.group("accession")) if match else ""


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
            from extensions import db  # ruff:ignore[import-outside-top-level]
            from models import AmberJob, GromacsJob  # ruff:ignore[import-outside-top-level]

            # Determine job type by checking for engine-specific fields
            if job_data.get("prmtop_name"):
                # AMBER job
                amber_job = AmberJob.query.filter_by(id=job_id).first()
                if amber_job is not None:
                    amber_job._performance = 62.5  # ruff:ignore[private-member-access]
                    amber_job._finish_timestamp = int(time.time())  # ruff:ignore[private-member-access]
                    db.session.commit()
            else:
                # GROMACS job (default)
                gmx_job = GromacsJob.query.filter_by(id=job_id).first()
                if gmx_job is not None:
                    gmx_job._performance = 62.5  # ruff:ignore[private-member-access]
                    gmx_job._finish_timestamp = int(time.time())  # ruff:ignore[private-member-access]
                    db.session.commit()
        except Exception:
            pass


def _advance_gmx_tuner_status(status: dict) -> None:
    """
    Advance GMX tuner job state based on elapsed time.

    Deterministic pattern: even-indexed trials TERMINATE, odd-indexed trials ERROR.
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

    trial_configs = [
        {"np": 8, "ntomp": 1, "nb": "cpu", "pme": "cpu"},
        {"np": 4, "ntomp": 2, "nb": "cpu", "pme": "cpu"},
        {"np": 2, "ntomp": 4, "nb": "cpu", "pme": "cpu"},
        {"np": 8, "ntomp": 1, "nb": "gpu", "pme": "cpu"},
        {"np": 4, "ntomp": 2, "nb": "gpu", "pme": "gpu"},
        {"np": 2, "ntomp": 4, "nb": "gpu", "pme": "gpu"},
    ]
    config = trial_configs[len(trials) % len(trial_configs)]
    trials.append({
        "id": f"trial-{len(trials):05d}",
        "status": "RUNNING",
        **config,
        "performance": None,
        "started_at": now,
    })


def _advance_amber_tuner_status(status: dict) -> None:
    """
    Advance AMBER tuner job state based on elapsed time.

    Deterministic pattern: even-indexed trials TERMINATE, odd-indexed trials ERROR.
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
            if trial_idx % 2 == 0:
                running_trial["status"] = "TERMINATED"
                base_perf = 60.0
                if running_trial.get("binary") == "pmemd.cuda":
                    base_perf += 20.0
                if running_trial.get("ewald") == "optimized":
                    base_perf += 5.0
                running_trial["performance"] = base_perf + trial_idx
            else:
                running_trial["status"] = "ERROR"
                running_trial["performance"] = None
        return

    max_trials = int(status.get("max_trials", DEFAULT_TUNER_MAX_TRIALS))
    if len(trials) >= max_trials:
        status["status"] = "TERMINATED"
        return

    trial_configs = [
        {"np": 4, "ntomp": 1, "binary": "pmemd.cuda", "ewald": "default"},
        {"np": 1, "ntomp": 4, "binary": "pmemd.MPI", "ewald": "default"},
        {"np": 4, "ntomp": 1, "binary": "pmemd.cuda", "ewald": "optimized"},
        {"np": 2, "ntomp": 2, "binary": "pmemd.MPI", "ewald": "optimized"},
    ]
    config = trial_configs[len(trials) % len(trial_configs)]
    trials.append({
        "id": f"trial-{len(trials):05d}",
        "status": "RUNNING",
        **config,
        "performance": None,
        "started_at": now,
    })
