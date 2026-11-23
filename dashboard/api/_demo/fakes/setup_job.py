"""
Stand-in for the headless setup Job: advance the status doc through fake steps, then write a manifest.

A notebook containing `mddash-demo: fail` fails at FAIL_AT, so the Fix-in-notebook path is reachable.
"""

import threading
import time
from datetime import UTC, datetime

from core.config import DATA_DIR
from core.enums import Engine
from core.worker_jobs import write_status_doc

from ..files import ensure_amber_demo_files, ensure_demo_files, write_amber_simulation, write_gmx_simulation
from ..state import E2E, demo_state

STEPS = (
    "Fetch the input structure",
    "Build the topology",
    "Solvate",
    "Add ions",
    "Energy minimization",
    "NVT equilibration",
    "NPT equilibration",
    "Write the simulation manifest",
)
FAIL_AT = 4
FAIL_MARKER = "mddash-demo: fail"
STEP_SEC = 0.3 if E2E else 1.5
MANIFEST = "md.simulation.json"


def start_setup_job(job_name: str, experiment_id: str, engine: Engine, notebook: str, status: str) -> None:
    """Run the fake Job on a daemon thread."""
    demo_state.setup_jobs[job_name] = "active"
    threading.Thread(target=_run, args=(job_name, experiment_id, engine, notebook, status), daemon=True).start()


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _run(job_name: str, experiment_id: str, engine: Engine, notebook: str, status: str) -> None:
    exp_dir = DATA_DIR / experiment_id
    doc_path = exp_dir / status
    fails = FAIL_MARKER in (exp_dir / notebook).read_text(encoding="utf-8", errors="replace")
    doc = {"state": "running", "step": 0, "total": len(STEPS), "title": None, "started_at": _now(), "manifests": []}

    time.sleep(STEP_SEC)  # the pod "starting"
    for number, title in enumerate(STEPS, start=1):
        if demo_state.setup_jobs.get(job_name) != "active":
            return  # stopped: the API owns the doc now
        write_status_doc(doc_path, doc | {"step": number, "title": title})
        time.sleep(STEP_SEC)
        if fails and number == FAIL_AT:
            error = {"step": number, "cell": 7, "ename": "ValueError", "evalue": "Box is smaller than the cut-off"}
            write_status_doc(doc_path, doc | {"step": number, "title": title, "state": "failed", "error": error})
            demo_state.setup_jobs[job_name] = "failed"
            return

    _write_manifest(experiment_id, engine)
    write_status_doc(
        doc_path,
        doc | {"step": len(STEPS), "title": STEPS[-1], "state": "done", "finished_at": _now(), "manifests": [MANIFEST]},
    )
    demo_state.setup_jobs[job_name] = "complete"


def _write_manifest(experiment_id: str, engine: Engine) -> None:
    if engine is Engine.AMBER:
        ensure_amber_demo_files(experiment_id, prmtop_name="md.prmtop", inpcrd_name="md.inpcrd", mdin_names=["md.mdin"])
        write_amber_simulation(
            experiment_id, "md", MANIFEST, topology="md.prmtop", coordinates="md.inpcrd", control="md.mdin"
        )
    else:
        ensure_demo_files(experiment_id, ["md.tpr"])
        write_gmx_simulation(experiment_id, "md", MANIFEST, topology="md.tpr")
