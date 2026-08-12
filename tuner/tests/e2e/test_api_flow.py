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
TERMINAL_STATUSES = {"FINISHED", "ERROR"}
ACTIVE_STATUSES = {"PENDING", "RUNNING"}

COST_CPU_CORE_HOUR = float(os.environ["COST_CPU_CORE_HOUR"])
COST_GPU_HOUR = float(os.environ["COST_GPU_HOUR"])
COST_GB_RAM_HOUR = float(os.environ["COST_GB_RAM_HOUR"])
RAM_GB_PER_RANK = 4.0

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


def _trial_hourly_cost(engine: str, trial: dict[str, Any]) -> float:
    """Hourly cost of a trial's production resource footprint on this deployment's rates."""
    if engine == "gmx":
        cores = trial["np"] * (trial["ntomp"] if trial["ntomp"] > 0 else 1)
        gpus = int(trial["nb"] == "gpu" or trial["pme"] == "gpu")
        ram_gb = RAM_GB_PER_RANK * trial["np"]
    elif trial["binary"] == "pmemd.MPI":
        cores, gpus, ram_gb = trial["np"] * trial["ntomp"], 0, RAM_GB_PER_RANK * trial["np"]
    else:
        cores, gpus, ram_gb = trial["ntomp"], 1, RAM_GB_PER_RANK
    return cores * COST_CPU_CORE_HOUR + gpus * COST_GPU_HOUR + ram_gb * COST_GB_RAM_HOUR


def _assert_estimates(
    status: dict[str, Any],
    engine: str,
    expected_sim_length_ns: float | None = None,
) -> None:
    """Validate sim_length_ns and per-trial estimated_time/estimated_cost on a terminal job."""
    sim_length = status.get("sim_length_ns")
    assert isinstance(sim_length, (int, float)), f"{engine}: sim_length_ns missing: {sim_length!r}"
    assert sim_length > 0, f"{engine}: expected positive sim_length_ns, got {sim_length!r}"
    if expected_sim_length_ns is not None:
        assert sim_length == pytest.approx(expected_sim_length_ns)

    finished = [t for t in status["trials"] if t["status"] == "FINISHED"]
    assert finished, f"{engine}: no FINISHED trials to validate estimates"

    for trial in status["trials"]:
        if trial["status"] != "FINISHED":
            assert trial["estimated_time"] is None
            assert trial["estimated_cost"] is None
            continue
        performance = trial["performance"]
        assert isinstance(performance, (int, float))
        assert performance > 0
        expected_time = sim_length / performance * 24.0
        assert trial["estimated_time"] == pytest.approx(expected_time, rel=1e-9)
        assert trial["estimated_time"] > 0
        assert trial["estimated_cost"] == pytest.approx(expected_time * _trial_hourly_cost(engine, trial), rel=1e-9)
        assert trial["estimated_cost"] > 0


def _mdin_sim_length_ns(mdin_path: Path) -> float:
    """Compute the simulation length (ns) of the demo mdin: nstlim * dt / 1000."""
    import re

    text = mdin_path.read_text(encoding="utf-8")
    nstlim = re.search(r"nstlim\s*=\s*(\d+)", text)
    dt = re.search(r"\bdt\s*=\s*([\d.eE+-]+)", text)
    assert nstlim, f"could not parse nstlim from {mdin_path}"
    assert dt, f"could not parse dt from {mdin_path}"
    return int(nstlim.group(1)) * float(dt.group(1)) / 1000.0


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
        assert status["status"] == "FINISHED", status.get("error")
        _assert_estimates(status, "gmx")
    finally:
        if job_id:
            _delete_job(client, "gmx", job_id)

    deleted_status = client.get(f"tuning-jobs/gmx/{job_id}/status")
    assert deleted_status.status_code == 404


def test_gromacs_nsteps_override_flow(client: httpx.Client) -> None:
    job_id: str | None = None
    demo_file = ROOT_DIR / "demo" / "gmx" / "md.tpr"

    with demo_file.open("rb") as tpr_file:
        response = client.post(
            "tuning-jobs/gmx",
            files={"file": (demo_file.name, tpr_file, "application/octet-stream")},
            data={"nsteps": N_STEPS, "extra_args": "-nsteps 100000"},
        )

    if response.status_code == 400:
        pytest.skip("deployment predates -nsteps override support")
    response.raise_for_status()
    assert response.status_code == 201
    job_id = response.json()["id"]

    try:
        status = _poll_until_finished(client, "gmx", job_id)
        assert status["status"] == "FINISHED", status.get("error")
        _assert_estimates(status, "gmx")
    finally:
        if job_id:
            _delete_job(client, "gmx", job_id)


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
        assert status["status"] == "FINISHED", status.get("error")
        _assert_estimates(status, "amber", expected_sim_length_ns=_mdin_sim_length_ns(mdin_path))
    finally:
        if job_id:
            _delete_job(client, "amber", job_id)

    deleted_status = client.get(f"tuning-jobs/amber/{job_id}/status")
    assert deleted_status.status_code == 404
