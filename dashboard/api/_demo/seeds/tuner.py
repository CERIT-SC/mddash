"""Seeded tuner jobs; live ones are driven by the fake tuner API."""

import time
from datetime import datetime, timedelta

from core.enums import JobStatus
from modules.models import Experiment, TunerJob

from ..state import build_model, demo_state
from .experiments import ENZYME, MEMBRANE


def _trial(trial_id: str, status: JobStatus, np: int, ntomp: int, nb: str, pme: str, performance: float | None) -> dict:
    return {
        "id": trial_id,
        "status": status.value,
        "np": np,
        "ntomp": ntomp,
        "nb": nb,
        "pme": pme,
        "performance": performance,
    }


def seed_tuner_jobs(experiments: dict[str, Experiment], now: datetime) -> list[TunerJob]:
    """Build the tuner jobs and register the live ones with the fake tuner."""
    # Running tuner keeps the membrane protein at the tune step; the mock rolls
    # a window of max_trials trials forever (never FINISHED).
    membrane_tuner = build_model(
        TunerJob,
        experiment=experiments[MEMBRANE],
        simulation_path="gpcr_membrane.simulation.json",
        id="demo-tuner-membrane",
        nsteps=10000,
        created_at=now - timedelta(hours=2),
        is_stopped=False,
        error_message=None,
    )
    demo_state.tuner_jobs[membrane_tuner.id] = {
        "status": JobStatus.RUNNING.value,
        "created_at": time.time() - 4,
        "max_trials": 10,
        "trials": [
            _trial("membrane_00000", JobStatus.FINISHED, 8, 1, "gpu", "cpu", 58.2),
            _trial("membrane_00001", JobStatus.ERROR, 4, 2, "cpu", "cpu", None),
            _trial("membrane_00002", JobStatus.RUNNING, 4, 2, "gpu", "gpu", None),
        ],
    }

    enzyme = experiments[ENZYME]
    running_tuner = build_model(
        TunerJob,
        experiment=enzyme,
        simulation_path="md.simulation.json",
        id="demo-tuner-prod",
        nsteps=25000,
        created_at=now - timedelta(hours=8),
        is_stopped=False,
        error_message=None,
    )
    started_at = time.time() - 4
    demo_state.tuner_jobs[running_tuner.id] = {
        "status": JobStatus.RUNNING.value,
        "created_at": started_at,
        "max_trials": 12,
        "trials": [
            # Matches the seeded running production job's config, so the
            # Run step shows tuned estimates for "Configuration used".
            _trial("prod_00000", JobStatus.FINISHED, 4, 2, "gpu", "cpu", 704.12),
            _trial("prod_00001", JobStatus.ERROR, 4, 2, "cpu", "cpu", None),
            {**_trial("prod_00002", JobStatus.RUNNING, 4, 2, "gpu", "gpu", None), "started_at": started_at},
        ],
    }

    # Stopped tuner of the equilibration phase: its trials are preserved dashboard-side.
    stopped_tuner = build_model(
        TunerJob,
        experiment=enzyme,
        simulation_path="npt_equilibration.simulation.json",
        id="demo-tuner-npt",
        nsteps=25000,
        created_at=now - timedelta(hours=9),
        is_stopped=True,
        _preserved_trials=[
            _trial("npt_00000", JobStatus.FINISHED, 8, 1, "gpu", "cpu", 68.2),
            _trial("npt_00001", JobStatus.FINISHED, 4, 2, "gpu", "gpu", 71.8),
        ],
        error_message=None,
    )

    error_tuner = build_model(
        TunerJob,
        experiment=enzyme,
        simulation_path="hiv_protease_apo_enzyme_wild_type_production_run_2024.simulation.json",
        id="demo-tuner-failed",
        nsteps=25000,
        created_at=now - timedelta(hours=10),
        is_stopped=False,
        error_message="Failed to submit to tuner: Connection timeout after 30s",
    )

    return [membrane_tuner, running_tuner, stopped_tuner, error_tuner]
