"""Seeded GROMACS/AMBER production runs, their fake MDRun state, and the logs they left."""

import time
from datetime import datetime, timedelta

from core.enums import AmberBinary, DeviceType, Engine, EwaldPreset, JobStatus
from modules.models import AmberJob, Experiment, GromacsJob, SimulationJob

from ..files import (
    append_gmx_stopped_segment,
    write_finished_amber_log,
    write_finished_gmx_log,
    write_gmx_checkpoint,
    write_mdrun_stdio,
    write_running_amber_log,
    write_running_gmx_log,
)
from ..state import E2E, build_model, demo_state
from .experiments import AMBER_DNA, AMBER_FOLDING, E2E_GMX_STUDIES, ENZYME, PUBLISHED

RUNNING_GMX = "demo-gmx-running"
RUNNING_AMBER = "demo-amber-running"
STOPPED_GMX_STARTED_HOURS_AGO = 19


def _mdrun(job: SimulationJob, status: JobStatus, nsteps: int, **inputs: object) -> None:
    demo_state.mdrun_jobs[job.id] = {
        "status": status.value,
        "experiment_id": job.experiment.id,
        "nsteps": nsteps,
        **inputs,
    }


def seed_runs(experiments: dict[str, Experiment], now: datetime) -> list[SimulationJob]:
    """Build the production runs and register them with the fake MDRun."""
    enzyme = experiments[ENZYME]
    running_gmx = build_model(
        GromacsJob,
        id=RUNNING_GMX,
        experiment=enzyme,
        simulation_path="md.simulation.json",
        pme=DeviceType.CPU,
        nb=DeviceType.GPU,
        np=4,
        ntomp=2,
        _nsteps=50000,  # matches the step count in the demo md.log template
        # Log appends are timestamped "now", so an old start would inflate the ETA.
        _start_timestamp=int(now.timestamp()),
        _finish_timestamp=None,
        _performance=None,
        created_at=now - timedelta(hours=3),
    )
    _mdrun(
        running_gmx,
        JobStatus.RUNNING,
        50000,
        tpr_name="production/md.tpr",
        created_at=time.time(),
        duration_sec=600,
        log_line_index=0,
        log_total_lines=500,
    )

    # A run of NPT equilibration extended past its finished first block and then
    # stopped: exercises non-destructive stop and extend-from-checkpoint.
    stopped_gmx = build_model(
        GromacsJob,
        id="demo-gmx-stopped",
        experiment=enzyme,
        simulation_path="npt_equilibration.simulation.json",
        pme=DeviceType.CPU,
        nb=DeviceType.GPU,
        np=8,
        ntomp=1,
        _nsteps=150000,
        _init_step=100000,
        _start_timestamp=int((now - timedelta(hours=STOPPED_GMX_STARTED_HOURS_AGO)).timestamp()),
        _finish_timestamp=None,
        _performance=None,
        _last_known_status=JobStatus.STOPPED,
        created_at=now - timedelta(hours=STOPPED_GMX_STARTED_HOURS_AGO),
    )
    _mdrun(stopped_gmx, JobStatus.STOPPED, 150000, tpr_name="npt_equilibration.tpr")

    published_gmx = build_model(
        GromacsJob,
        id="demo-gmx-published",
        experiment=experiments[PUBLISHED],
        simulation_path="lysozyme_hewl.simulation.json",
        pme=DeviceType.CPU,
        nb=DeviceType.CPU,
        np=4,
        ntomp=4,
        _nsteps=1000000,
        _start_timestamp=int((now - timedelta(days=9)).timestamp()),
        _finish_timestamp=int((now - timedelta(days=8, hours=4)).timestamp()),
        _performance=45.3,
        created_at=now - timedelta(days=9),
    )
    _mdrun(published_gmx, JobStatus.FINISHED, 1000000, tpr_name="lysozyme_hewl.tpr")

    amber_folding = experiments[AMBER_FOLDING]
    # Finished AMBER production job (villin), so the villin simulation genuinely
    # owns the analyze phase; its analyses are seeded too.
    production_amber = build_model(
        AmberJob,
        id="demo-amber-production",
        experiment=amber_folding,
        simulation_path="villin.simulation.json",
        binary=AmberBinary.PMEMD_CUDA,
        ewald=EwaldPreset.OPTIMIZED,
        np=1,
        ntomp=8,
        _nsteps=500000,
        _start_timestamp=int((now - timedelta(hours=3)).timestamp()),
        _finish_timestamp=int((now - timedelta(minutes=10)).timestamp()),
        _performance=41.2,
        created_at=now - timedelta(hours=2),
        engine=Engine.AMBER,
    )
    villin_inputs = {"prmtop_name": "villin.prmtop", "inpcrd_name": "villin.inpcrd"}
    _mdrun(production_amber, JobStatus.FINISHED, 500000, **villin_inputs, mdin_name="production.mdin")

    # Exercises the AMBER stop flow (mirrors the enzyme study's live GMX job).
    running_amber = build_model(
        AmberJob,
        id=RUNNING_AMBER,
        experiment=amber_folding,
        simulation_path="equilibration.simulation.json",
        binary=AmberBinary.PMEMD_MPI,
        ewald=EwaldPreset.DEFAULT,
        np=4,
        ntomp=2,
        _nsteps=100000,
        _start_timestamp=int((now - timedelta(minutes=30)).timestamp()),
        created_at=now - timedelta(minutes=40),
        engine=Engine.AMBER,
    )
    _mdrun(running_amber, JobStatus.RUNNING, 100000, **villin_inputs, mdin_name="equilibration.mdin")

    finished_amber_dna = build_model(
        AmberJob,
        id="demo-amber-dna",
        experiment=experiments[AMBER_DNA],
        simulation_path="dna.simulation.json",
        binary=AmberBinary.PMEMD_CUDA,
        ewald=EwaldPreset.OPTIMIZED,
        np=1,
        ntomp=4,
        _nsteps=2000000,
        _start_timestamp=int((now - timedelta(days=6)).timestamp()),
        _finish_timestamp=int((now - timedelta(days=5)).timestamp()),
        _performance=156.2,
        created_at=now - timedelta(days=6),
        engine=Engine.AMBER,
    )
    _mdrun(
        finished_amber_dna,
        JobStatus.FINISHED,
        2000000,
        prmtop_name="dna.prmtop",
        inpcrd_name="dna.inpcrd",
        mdin_name="simulation.mdin",
    )

    runs: list[SimulationJob] = [
        running_gmx,
        stopped_gmx,
        published_gmx,
        production_amber,
        running_amber,
        finished_amber_dna,
    ]
    if E2E:
        for study in E2E_GMX_STUDIES:
            started = now - timedelta(days=study.age_days)
            job = build_model(
                GromacsJob,
                id=f"demo-gmx-{study.sim_name}",
                experiment=experiments[study.experiment_id],
                simulation_path=f"{study.sim_name}.simulation.json",
                pme=DeviceType.CPU,
                nb=study.nb,
                np=study.ranks,
                ntomp=study.threads,
                _nsteps=study.nsteps,
                _start_timestamp=int(started.timestamp()),
                _finish_timestamp=int((started + timedelta(hours=12)).timestamp()),
                _performance=study.performance,
                created_at=started,
            )
            _mdrun(job, JobStatus.FINISHED, study.nsteps, tpr_name=study.tpr_name)
            runs.append(job)
    return runs


def write_run_outputs(now: datetime) -> None:
    """Write the logs, stdio, and checkpoints the seeded runs left (input files must exist)."""
    write_running_gmx_log(ENZYME, "production/md")
    write_finished_gmx_log(ENZYME, "npt_equilibration", nsteps=100000, performance=68.5)
    write_mdrun_stdio(ENZYME, "production", RUNNING_GMX)
    # The stopped run is resumable via its checkpoint.
    write_gmx_checkpoint(ENZYME, "npt_equilibration")
    # TERM-stopped runs leave a Performance line the parsers must not trust.
    append_gmx_stopped_segment(
        ENZYME,
        "npt_equilibration",
        init_step=100000,
        nsteps=150000,
        done_steps=120000,
        started=now - timedelta(hours=STOPPED_GMX_STARTED_HOURS_AGO),
    )

    write_finished_gmx_log(PUBLISHED, "lysozyme_hewl", nsteps=1000000, performance=45.3)

    write_finished_amber_log(AMBER_FOLDING, "production")
    write_running_amber_log(AMBER_FOLDING, "equilibration")
    write_mdrun_stdio(AMBER_FOLDING, "", RUNNING_AMBER)

    write_finished_amber_log(AMBER_DNA, "simulation")

    if E2E:
        for study in E2E_GMX_STUDIES:
            write_finished_gmx_log(
                study.experiment_id, study.sim_name, nsteps=study.nsteps, performance=study.performance
            )
