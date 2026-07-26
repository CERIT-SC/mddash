"""
End-to-end API flow tests against a running MD Tuner API.

These tests are excluded from the default unit test run. Run with:
    E2E_API_BASE_URL=https://example.test/api pytest tests/e2e
"""

from __future__ import annotations

import os
import time
from pathlib import Path
from typing import TYPE_CHECKING, Any

import httpx
import pytest

if TYPE_CHECKING:
    from collections.abc import Iterator

AUTH = (os.getenv("E2E_TUNER_USER", ""), os.getenv("E2E_TUNER_PASSWORD", ""))
BASE_URL = os.getenv("E2E_API_BASE_URL")
POLL_INTERVAL_SECONDS = 10
POLL_TIMEOUT_SECONDS = 1800
N_STEPS = "1000"
ROOT_DIR = Path(__file__).resolve().parents[2]
TERMINAL_STATUSES = {"TERMINATED", "ERROR"}
ACTIVE_STATUSES = {"PENDING", "RUNNING"}

pytestmark = pytest.mark.e2e


def _require_base_url() -> str:
    if not BASE_URL:
        pytest.skip("Set E2E_API_BASE_URL to run API E2E tests")
    return BASE_URL.rstrip("/")


def _require_auth() -> tuple[str, str]:
    if not all(AUTH):
        pytest.skip("Set E2E_TUNER_USER and E2E_TUNER_PASSWORD to run API E2E tests")
    return AUTH


@pytest.fixture(scope="module")
def client() -> Iterator[httpx.Client]:
    with httpx.Client(base_url=_require_base_url(), auth=_require_auth(), timeout=120.0) as api_client:
        response = api_client.get("health")
        response.raise_for_status()
        assert response.json() == {"status": "ok"}
        yield api_client


def _poll_until_finished(client: httpx.Client, engine: str, job_id: str) -> dict[str, Any]:
    deadline = time.monotonic() + POLL_TIMEOUT_SECONDS
    last_status: dict[str, Any] | None = None

    while time.monotonic() < deadline:
        response = client.get(f"tuning-jobs/{engine}/{job_id}/status")
        response.raise_for_status()
        last_status = response.json()

        assert last_status["id"] == job_id
        assert last_status["status"] in ACTIVE_STATUSES | TERMINAL_STATUSES
        assert isinstance(last_status["trials"], list)

        if last_status["status"] in TERMINAL_STATUSES:
            return last_status

        time.sleep(POLL_INTERVAL_SECONDS)

    pytest.fail(f"Timed out waiting for {engine} job {job_id}; last status: {last_status}")


def _delete_job(client: httpx.Client, engine: str, job_id: str) -> None:
    response = client.delete(f"tuning-jobs/{engine}/{job_id}")
    assert response.status_code == 204


def test_gromacs_api_flow(client: httpx.Client) -> None:
    job_id: str | None = None
    demo_file = ROOT_DIR / "demo" / "gmx" / "md.tpr"

    with demo_file.open("rb") as tpr_file:
        response = client.post(
            "tuning-jobs/gmx",
            files={"file": (demo_file.name, tpr_file, "application/octet-stream")},
            data={"nsteps": N_STEPS},
        )

    response.raise_for_status()
    assert response.status_code == 201
    created_job = response.json()
    job_id = created_job["id"]
    assert created_job["status"] == "PENDING"

    try:
        status = _poll_until_finished(client, "gmx", job_id)
        assert status["trials"]
        assert status["status"] == "TERMINATED", status.get("error")
    finally:
        if job_id:
            _delete_job(client, "gmx", job_id)

    deleted_status = client.get(f"tuning-jobs/gmx/{job_id}/status")
    assert deleted_status.status_code == 404


def test_amber_api_flow(client: httpx.Client) -> None:
    job_id: str | None = None
    demo_dir = ROOT_DIR / "demo" / "amber"
    prmtop_path = demo_dir / "RAMP1.prmtop"
    inpcrd_path = demo_dir / "RAMP1_equil.rst7"
    mdin_path = demo_dir / "md.mdin"

    with (
        prmtop_path.open("rb") as prmtop_file,
        inpcrd_path.open("rb") as inpcrd_file,
        mdin_path.open("rb") as mdin_file,
    ):
        response = client.post(
            "tuning-jobs/amber",
            files={
                "prmtop": (prmtop_path.name, prmtop_file, "application/octet-stream"),
                "inpcrd": (inpcrd_path.name, inpcrd_file, "application/octet-stream"),
                "mdin": (mdin_path.name, mdin_file, "text/plain"),
            },
            data={"nsteps": N_STEPS},
        )

    response.raise_for_status()
    assert response.status_code == 201
    created_job = response.json()
    job_id = created_job["id"]
    assert created_job["status"] == "PENDING"

    try:
        status = _poll_until_finished(client, "amber", job_id)
        assert status["trials"]
        assert status["status"] == "TERMINATED", status.get("error")
    finally:
        if job_id:
            _delete_job(client, "amber", job_id)

    deleted_status = client.get(f"tuning-jobs/amber/{job_id}/status")
    assert deleted_status.status_code == 404
