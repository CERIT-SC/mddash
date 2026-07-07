import json
import logging
import time
from datetime import datetime, timedelta

import requests
from config import DATA_DIR
from enums import AmberBinary, AnalysisType, DeviceType, Engine, EwaldPreset, JobStatus, PodStatus
from extensions import db
from models import AmberJob, AnalysisJob, Experiment, GromacsJob, Notebook, TunerJob
from models.analysis_job import ANALYSIS_RESULT_PREFIX, ANALYSIS_RESULT_SUFFIX, mwf_output_dir

from .files import (
    MDPOSIT_DEMO_PROJECT_URL,
    ensure_amber_demo_files,
    ensure_demo_files,
    ensure_mdposit_demo_files,
    ensure_schema_files,
    write_amber_simulation,
    write_finished_gmx_log,
    write_gmx_simulation,
    write_running_gmx_log,
)
from .state import build_model, demo_state

logger = logging.getLogger(__name__)


def seed_data() -> None:  # noqa: PLR0914
    demo_state.reset()

    if Experiment.query.count() > 0:
        _rehydrate_runtime_state()
        return

    now = datetime.now()

    # Experiment 1: Membrane protein simulation (fresh setup, not running yet)
    membrane = build_model(
        Experiment,
        id="aaaaa",
        name="GPCR membrane protein in lipid bilayer",
        source_message="Created by uploading files: gpcr_membrane.tpr, structure.pdb.",
        notebooks_repo="https://github.com/sb-ncbr/mddash-notebooks.git",
        created_at=now - timedelta(days=3),
        updated_at=now - timedelta(days=2),
    )
    membrane_notebook = build_model(Notebook, experiment_id=membrane.id, token="demo-token-membrane")
    demo_state.notebook_status[membrane.id] = PodStatus.DOWN

    # Experiment 2: Active enzyme simulation (currently running)
    enzyme = build_model(
        Experiment,
        id="bbbbb",
        name="HIV protease inhibitor binding study",
        source_message="Created by downloading repository from 'https://zenodo.org/records/7261108'.",
        notebooks_repo="https://github.com/sb-ncbr/mddash-notebooks.git",
        created_at=now - timedelta(days=2),
        updated_at=now - timedelta(days=1),
    )
    enzyme_notebook = build_model(Notebook, experiment_id=enzyme.id, token="demo-token-enzyme")
    demo_state.notebook_status[enzyme.id] = PodStatus.RUNNING

    # Running tuner job for the main production run
    running_tuner = build_model(
        TunerJob,
        experiment=enzyme,
        simulation_path="md.simulation.json",
        id="demo-tuner-prod",
        created_at=now - timedelta(hours=8),
        is_stopped=False,
        error_message=None,
    )
    if running_tuner.id:
        started_at = time.time() - 4
        demo_state.tuner_jobs[running_tuner.id] = {
            "status": JobStatus.RUNNING.value,
            "created_at": started_at,
            "max_trials": 4,
            "trials": [
                {
                    "id": "prod_00000",
                    "status": JobStatus.TERMINATED.value,
                    "np": 8,
                    "ntomp": 1,
                    "nb": "gpu",
                    "pme": "cpu",
                    "performance": 72.4,
                },
                {
                    "id": "prod_00001",
                    "status": JobStatus.ERROR.value,
                    "np": 4,
                    "ntomp": 2,
                    "nb": "cpu",
                    "pme": "cpu",
                    "performance": None,
                },
                {
                    "id": "prod_00002",
                    "status": JobStatus.RUNNING.value,
                    "np": 4,
                    "ntomp": 2,
                    "nb": "gpu",
                    "pme": "gpu",
                    "performance": None,
                    "started_at": started_at,
                },
            ],
        }

    # Stopped/completed tuner job from equilibration phase
    stopped_tuner = build_model(
        TunerJob,
        experiment=enzyme,
        simulation_path="npt_equilibration.simulation.json",
        id="demo-tuner-npt",
        created_at=now - timedelta(hours=9),
        is_stopped=True,
        _preserved_trials=[
            {
                "id": "npt_00000",
                "status": JobStatus.TERMINATED.value,
                "np": 8,
                "ntomp": 1,
                "nb": "gpu",
                "pme": "cpu",
                "performance": 68.2,
            },
            {
                "id": "npt_00001",
                "status": JobStatus.TERMINATED.value,
                "np": 4,
                "ntomp": 2,
                "nb": "gpu",
                "pme": "gpu",
                "performance": 71.8,
            },
        ],
        error_message=None,
    )

    # Failed tuner job
    error_tuner = build_model(
        TunerJob,
        experiment=enzyme,
        simulation_path="hiv_protease_apo_enzyme_wild_type_production_run_2024.simulation.json",
        id="demo-tuner-failed",
        created_at=now - timedelta(hours=10),
        is_stopped=False,
        error_message="Failed to submit to tuner: Connection timeout after 30s",
    )

    # Running MD simulation (production run in progress)
    running_gmx = build_model(
        GromacsJob,
        id="demo-gmx-running",
        experiment=enzyme,
        simulation_path="md.simulation.json",
        pme=DeviceType.CPU,
        nb=DeviceType.GPU,
        np=4,
        ntomp=2,
        _nsteps=500000,
        _start_timestamp=int((now - timedelta(hours=3)).timestamp()),
        _finish_timestamp=None,
        _performance=None,
        created_at=now - timedelta(hours=3),
    )
    demo_state.mdrun_jobs[running_gmx.id] = {
        "status": JobStatus.RUNNING.value,
        "experiment_id": enzyme.id,
        "tpr_name": "production/md.tpr",
        "nsteps": 500000,
        "created_at": time.time(),
        "duration_sec": 3600,
    }

    # Finished MD simulation (NPT equilibration complete)
    finished_gmx = build_model(
        GromacsJob,
        id="demo-gmx-finished",
        experiment=enzyme,
        simulation_path="npt_equilibration.simulation.json",
        pme=DeviceType.CPU,
        nb=DeviceType.GPU,
        np=8,
        ntomp=1,
        _nsteps=100000,
        _start_timestamp=int((now - timedelta(days=1)).timestamp()),
        _finish_timestamp=int((now - timedelta(hours=20)).timestamp()),
        _performance=68.5,
        created_at=now - timedelta(days=1),
    )
    demo_state.mdrun_jobs[finished_gmx.id] = {
        "status": JobStatus.TERMINATED.value,
        "experiment_id": enzyme.id,
        "tpr_name": "npt_equilibration.tpr",
        "nsteps": 100000,
    }

    # Experiment 3: Published study (already completed and published to MDRepo)
    published = build_model(
        Experiment,
        id="ccccc",
        name="Hen egg-white lysozyme folding stability",
        source_message="Created by uploading files: lysozyme_hewl.tpr.",
        notebooks_repo="https://github.com/sb-ncbr/mddash-notebooks.git",
        mdrepo_id="8gahj-dh519",
        mdrepo_published=True,
        created_at=now - timedelta(days=10),
        updated_at=now - timedelta(days=8),
    )
    published_notebook = build_model(Notebook, experiment_id=published.id, token="demo-token-published")
    demo_state.notebook_status[published.id] = PodStatus.DOWN
    if published.mdrepo_id:
        demo_state.mdrepo_records[published.mdrepo_id] = True

    published_gmx = build_model(
        GromacsJob,
        id="demo-gmx-published",
        experiment=published,
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
    demo_state.mdrun_jobs[published_gmx.id] = {
        "status": JobStatus.TERMINATED.value,
        "experiment_id": published.id,
        "tpr_name": "lysozyme_hewl.tpr",
        "nsteps": 1000000,
    }

    # Analysis jobs for the published experiment (completed)
    rmsd_analysis = build_model(
        AnalysisJob,
        id="analysis-rmsd",
        experiment=published,
        simulation_path="lysozyme_hewl.simulation.json",
        analysis_name=AnalysisType.RMSDS,
        structure_file="structure.pdb",
        trajectory_file="trajectory.xtc",
        topology_file=None,
    )

    sasa_analysis = build_model(
        AnalysisJob,
        id="analysis-sasa",
        experiment=published,
        simulation_path="lysozyme_hewl.simulation.json",
        analysis_name=AnalysisType.SAS,
        structure_file="structure.pdb",
        trajectory_file="trajectory.xtc",
        topology_file=None,
    )

    # Analysis job for enzyme experiment (completed)
    hbonds_analysis = build_model(
        AnalysisJob,
        id="analysis-hbonds",
        experiment=enzyme,
        simulation_path="md.simulation.json",
        analysis_name=AnalysisType.HBONDS,
        structure_file="structure.pdb",
        trajectory_file="trajectory.xtc",
        topology_file=None,
    )

    # Experiment 4: AMBER protein folding study (currently running AMBER simulation)
    amber_folding = build_model(
        Experiment,
        id="ddddd",
        name="AMBER villin headpiece folding",
        source_message="Created by uploading files: villin.prmtop, villin.inpcrd, production.mdin.",
        notebooks_repo="https://github.com/sb-ncbr/mddash-notebooks.git",
        engine=Engine.AMBER,
        created_at=now - timedelta(hours=6),
        updated_at=now - timedelta(hours=2),
    )
    amber_folding_notebook = build_model(Notebook, experiment_id=amber_folding.id, token="demo-token-amber")
    demo_state.notebook_status[amber_folding.id] = PodStatus.RUNNING

    # Running AMBER job
    running_amber = build_model(
        AmberJob,
        id="demo-amber-running",
        experiment=amber_folding,
        simulation_path="villin.simulation.json",
        binary=AmberBinary.PMEMD_CUDA,
        ewald=EwaldPreset.OPTIMIZED,
        np=1,
        ntomp=8,
        _nsteps=500000,
        _start_timestamp=int((now - timedelta(hours=2)).timestamp()),
        _finish_timestamp=None,
        _performance=None,
        created_at=now - timedelta(hours=2),
        engine=Engine.AMBER,
    )
    demo_state.mdrun_jobs[running_amber.id] = {
        "status": JobStatus.RUNNING.value,
        "experiment_id": amber_folding.id,
        "prmtop_name": "villin.prmtop",
        "inpcrd_name": "villin.inpcrd",
        "mdin_name": "production.mdin",
        "nsteps": 500000,
        "created_at": time.time(),
        "duration_sec": 7200,
    }

    # Finished AMBER job (equilibration complete)
    finished_amber = build_model(
        AmberJob,
        id="demo-amber-finished",
        experiment=amber_folding,
        simulation_path="equilibration.simulation.json",
        binary=AmberBinary.PMEMD_MPI,
        ewald=EwaldPreset.DEFAULT,
        np=4,
        ntomp=2,
        _nsteps=100000,
        _start_timestamp=int((now - timedelta(hours=5)).timestamp()),
        _finish_timestamp=int((now - timedelta(hours=3)).timestamp()),
        _performance=28.7,
        created_at=now - timedelta(hours=5),
        engine=Engine.AMBER,
    )
    demo_state.mdrun_jobs[finished_amber.id] = {
        "status": JobStatus.TERMINATED.value,
        "experiment_id": amber_folding.id,
        "prmtop_name": "villin.prmtop",
        "inpcrd_name": "villin.inpcrd",
        "mdin_name": "equilibration.mdin",
        "nsteps": 100000,
    }

    # Experiment 5: Published AMBER DNA simulation
    amber_dna = build_model(
        Experiment,
        id="eeeee",
        name="AMBER DNA duplex stability",
        source_message="Created by uploading files: dna.prmtop, dna.inpcrd, simulation.mdin.",
        notebooks_repo="https://github.com/sb-ncbr/mddash-notebooks.git",
        engine=Engine.AMBER,
        created_at=now - timedelta(days=7),
        updated_at=now - timedelta(days=5),
    )
    amber_dna_notebook = build_model(Notebook, experiment_id=amber_dna.id, token="demo-token-dna")
    demo_state.notebook_status[amber_dna.id] = PodStatus.DOWN

    # Experiment 6: MDPosit-imported trajectory bundle
    mdposit_demo = build_model(
        Experiment,
        id="fffff",
        name="MDPosit imported lysozyme trajectory",
        source_message=f"Created by downloading repository from '{MDPOSIT_DEMO_PROJECT_URL}'.",
        notebooks_repo="https://github.com/sb-ncbr/mddash-notebooks.git",
        created_at=now - timedelta(days=1, hours=6),
        updated_at=now - timedelta(days=1),
    )
    mdposit_demo_notebook = build_model(Notebook, experiment_id=mdposit_demo.id, token="demo-token-mdposit")
    demo_state.notebook_status[mdposit_demo.id] = PodStatus.DOWN

    # Finished AMBER DNA job
    finished_amber_dna = build_model(
        AmberJob,
        id="demo-amber-dna",
        experiment=amber_dna,
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
    demo_state.mdrun_jobs[finished_amber_dna.id] = {
        "status": JobStatus.TERMINATED.value,
        "experiment_id": amber_dna.id,
        "prmtop_name": "dna.prmtop",
        "inpcrd_name": "dna.inpcrd",
        "mdin_name": "simulation.mdin",
        "nsteps": 2000000,
    }

    db.session.add_all([
        membrane,
        membrane_notebook,
        enzyme,
        enzyme_notebook,
        running_tuner,
        stopped_tuner,
        error_tuner,
        running_gmx,
        finished_gmx,
        published,
        published_notebook,
        published_gmx,
        rmsd_analysis,
        sasa_analysis,
        hbonds_analysis,
        amber_folding,
        amber_folding_notebook,
        running_amber,
        finished_amber,
        amber_dna,
        amber_dna_notebook,
        finished_amber_dna,
        mdposit_demo,
        mdposit_demo_notebook,
    ])
    db.session.commit()

    # Seed files for each experiment
    # Membrane protein: standard files
    ensure_demo_files(membrane.id, ["gpcr_membrane.tpr", "structure.pdb", "trajectory.xtc"])

    # Enzyme study: includes subdirectory, long filename, and multiple runs
    ensure_demo_files(
        enzyme.id,
        [
            "production/md.tpr",  # Subdirectory file
            "npt_equilibration.tpr",
            "hiv_protease_apo_enzyme_wild_type_production_run_2024.tpr",  # Long filename
            "structure.pdb",
            "trajectory.xtc",
            "equilibration/nvt.tpr",  # Another subdirectory
        ],
    )
    write_running_gmx_log(enzyme.id, "production/md")
    write_finished_gmx_log(enzyme.id, "npt_equilibration", nsteps=100000, performance=68.5)

    # Published study: simple structure
    ensure_demo_files(published.id, ["lysozyme_hewl.tpr", "structure.pdb", "trajectory.xtc"])
    write_finished_gmx_log(published.id, "lysozyme_hewl", nsteps=1000000, performance=45.3)

    # AMBER villin folding study: uses AMBER file format
    ensure_amber_demo_files(
        amber_folding.id,
        prmtop_name="villin.prmtop",
        inpcrd_name="villin.inpcrd",
        mdin_names=["production.mdin", "equilibration.mdin"],
    )

    # AMBER DNA study: uses AMBER file format
    ensure_amber_demo_files(
        amber_dna.id,
        prmtop_name="dna.prmtop",
        inpcrd_name="dna.inpcrd",
        mdin_names=["simulation.mdin"],
    )

    # MDPosit import study: mirrors the project file layout exposed by HTTP mocks.
    ensure_mdposit_demo_files(mdposit_demo.id)

    # Seed schema files and simulation manifests for each experiment
    ensure_schema_files(membrane.id)
    write_gmx_simulation(membrane.id, "gpcr_membrane", topology="gpcr_membrane.tpr")

    ensure_schema_files(enzyme.id)
    write_gmx_simulation(enzyme.id, "md", simulation_path="md.simulation.json", topology="production/md.tpr")
    write_gmx_simulation(enzyme.id, "npt_equilibration", simulation_path="npt_equilibration.simulation.json")
    write_gmx_simulation(
        enzyme.id,
        "hiv_protease",
        simulation_path="hiv_protease_apo_enzyme_wild_type_production_run_2024.simulation.json",
        topology="hiv_protease_apo_enzyme_wild_type_production_run_2024.tpr",
    )

    ensure_schema_files(published.id)
    write_gmx_simulation(
        published.id,
        "lysozyme_hewl",
        simulation_path="lysozyme_hewl.simulation.json",
        topology="lysozyme_hewl.tpr",
    )

    ensure_schema_files(amber_folding.id)
    write_amber_simulation(
        amber_folding.id,
        "villin",
        simulation_path="villin.simulation.json",
        topology="villin.prmtop",
        coordinates="villin.inpcrd",
        control="production.mdin",
    )
    write_amber_simulation(
        amber_folding.id,
        "villin",
        simulation_path="equilibration.simulation.json",
        topology="villin.prmtop",
        coordinates="villin.inpcrd",
        control="equilibration.mdin",
    )

    ensure_schema_files(amber_dna.id)
    write_amber_simulation(
        amber_dna.id,
        "dna",
        simulation_path="dna.simulation.json",
        topology="dna.prmtop",
        coordinates="dna.inpcrd",
        control="simulation.mdin",
    )

    # Write analysis result files (fetched from MDposit)
    _fetch_and_write_analysis_results(published.id, "lysozyme_hewl.simulation.json", ["rmsds", "sasa"])
    _fetch_and_write_analysis_results(enzyme.id, "md.simulation.json", ["hbonds"])


def _fetch_and_write_analysis_results(experiment_id: str, simulation_path: str, analysis_names: list[str]) -> None:
    """Fetch analysis data from MDposit and write result files for seeding."""
    mdposit_analyses_url = "https://mdposit.mddbr.eu/api/rest/v1/projects/MD-A003ZT.2/analyses"

    # MDposit uses different endpoint names for some analysis types
    mdposit_name_map: dict[str, str] = {
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


    mwf_dir = DATA_DIR / experiment_id / mwf_output_dir(simulation_path)
    mwf_dir.mkdir(parents=True, exist_ok=True)

    headers = {"Accept": "application/json"}

    for analysis_name in analysis_names:
        mdposit_name = mdposit_name_map.get(analysis_name, analysis_name)
        try:
            response = requests.get(
                f"{mdposit_analyses_url}/{mdposit_name}",
                headers=headers,
                timeout=30,
            )
            if not response.ok:
                logger.warning("Failed to fetch %s from MDposit: %s", mdposit_name, response.status_code)
                continue

            data = response.json()
            filename = f"{ANALYSIS_RESULT_PREFIX}{mdposit_name.replace('-', '_')}{ANALYSIS_RESULT_SUFFIX}"
            (mwf_dir / filename).write_text(json.dumps(data), encoding="utf-8")

            # If the result is a summary list pointing to variants, fetch each one
            if isinstance(data, list):
                for item in data:
                    if not isinstance(item, dict):
                        continue
                    variant_name = item.get("analysis", "")
                    if not variant_name:
                        continue
                    variant_response = requests.get(
                        f"{mdposit_analyses_url}/{variant_name}",
                        headers=headers,
                        timeout=30,
                    )
                    if variant_response.ok:
                        variant_filename = (
                            f"{ANALYSIS_RESULT_PREFIX}{variant_name.replace('-', '_')}{ANALYSIS_RESULT_SUFFIX}"
                        )
                        (mwf_dir / variant_filename).write_text(json.dumps(variant_response.json()), encoding="utf-8")

            logger.debug("Fetched analysis %s for experiment %s", mdposit_name, experiment_id)

        except Exception:
            logger.exception("Failed to fetch analysis %s for seeding", mdposit_name)


def _rehydrate_runtime_state() -> None:  # noqa: PLR0912
    """Rehydrate runtime state from existing database records."""
    membrane = Experiment.query.filter_by(id="aaaaa").first()
    enzyme = Experiment.query.filter_by(id="bbbbb").first()
    published = Experiment.query.filter_by(id="ccccc").first()
    amber_folding = Experiment.query.filter_by(id="ddddd").first()
    amber_dna = Experiment.query.filter_by(id="eeeee").first()
    mdposit_demo = Experiment.query.filter_by(id="fffff").first()

    if membrane is not None:
        demo_state.notebook_status[membrane.id] = PodStatus.DOWN
        ensure_demo_files(membrane.id, ["gpcr_membrane.tpr", "structure.pdb", "trajectory.xtc"])

    if enzyme is not None:
        demo_state.notebook_status[enzyme.id] = PodStatus.RUNNING
        ensure_demo_files(
            enzyme.id,
            [
                "production/md.tpr",
                "npt_equilibration.tpr",
                "hiv_protease_apo_enzyme_wild_type_production_run_2024.tpr",
                "structure.pdb",
                "trajectory.xtc",
                "equilibration/nvt.tpr",
            ],
        )
        write_running_gmx_log(enzyme.id, "production/md")
        write_finished_gmx_log(enzyme.id, "npt_equilibration", nsteps=100000, performance=68.5)

    if published is not None:
        demo_state.notebook_status[published.id] = PodStatus.DOWN
        ensure_demo_files(published.id, ["lysozyme_hewl.tpr", "structure.pdb", "trajectory.xtc"])
        write_finished_gmx_log(published.id, "lysozyme_hewl", nsteps=1000000, performance=45.3)
        if published.mdrepo_id:
            demo_state.mdrepo_records[published.mdrepo_id] = True

    if amber_folding is not None:
        demo_state.notebook_status[amber_folding.id] = PodStatus.RUNNING
        ensure_amber_demo_files(
            amber_folding.id,
            prmtop_name="villin.prmtop",
            inpcrd_name="villin.inpcrd",
            mdin_names=["production.mdin", "equilibration.mdin"],
        )

    if amber_dna is not None:
        demo_state.notebook_status[amber_dna.id] = PodStatus.DOWN
        ensure_amber_demo_files(
            amber_dna.id,
            prmtop_name="dna.prmtop",
            inpcrd_name="dna.inpcrd",
            mdin_names=["simulation.mdin"],
        )

    if mdposit_demo is not None:
        demo_state.notebook_status[mdposit_demo.id] = PodStatus.DOWN
        ensure_mdposit_demo_files(mdposit_demo.id)

    # Re-seed schema files and simulation manifests for rehydrated experiments
    if membrane is not None:
        ensure_schema_files(membrane.id)
        write_gmx_simulation(membrane.id, "gpcr_membrane", topology="gpcr_membrane.tpr")

    if enzyme is not None:
        ensure_schema_files(enzyme.id)
        write_gmx_simulation(enzyme.id, "md", simulation_path="md.simulation.json", topology="production/md.tpr")
        write_gmx_simulation(enzyme.id, "npt_equilibration", simulation_path="npt_equilibration.simulation.json")
        write_gmx_simulation(
            enzyme.id,
            "hiv_protease",
            simulation_path="hiv_protease_apo_enzyme_wild_type_production_run_2024.simulation.json",
            topology="hiv_protease_apo_enzyme_wild_type_production_run_2024.tpr",
        )

    if published is not None:
        ensure_schema_files(published.id)
        write_gmx_simulation(
            published.id,
            "lysozyme_hewl",
            simulation_path="lysozyme_hewl.simulation.json",
            topology="lysozyme_hewl.tpr",
        )

    if amber_folding is not None:
        ensure_schema_files(amber_folding.id)
        write_amber_simulation(
            amber_folding.id,
            "villin",
            simulation_path="villin.simulation.json",
            topology="villin.prmtop",
            coordinates="villin.inpcrd",
            control="production.mdin",
        )
        write_amber_simulation(
            amber_folding.id,
            "villin",
            simulation_path="equilibration.simulation.json",
            topology="villin.prmtop",
            coordinates="villin.inpcrd",
            control="equilibration.mdin",
        )

    if amber_dna is not None:
        ensure_schema_files(amber_dna.id)
        write_amber_simulation(
            amber_dna.id,
            "dna",
            simulation_path="dna.simulation.json",
            topology="dna.prmtop",
            coordinates="dna.inpcrd",
            control="simulation.mdin",
        )

    # Rehydrate analysis jobs: any job with result files is treated as terminated.
    for job in AnalysisJob.query.all():
        job_name = f"analysis-{job.id}"
        demo_state.analysis_jobs[job_name] = {
            "status": JobStatus.TERMINATED.value,
            "experiment_id": job.experiment_id,
            "analysis_name": job.analysis_name.value,
        }

    # Rehydrate GROMACS jobs from database
    for gmx_job in GromacsJob.query.all():
        status = JobStatus.TERMINATED.value if gmx_job._finish_timestamp else JobStatus.RUNNING.value  # noqa: SLF001
        from models.simulation import Simulation  # noqa: PLC0415

        files = Simulation.get(gmx_job.experiment_id, gmx_job.simulation_path).resolved_files
        demo_state.mdrun_jobs[gmx_job.id] = {
            "status": status,
            "experiment_id": gmx_job.experiment_id,
            "tpr_name": files.get("topology", "md.tpr"),
            "nsteps": gmx_job._nsteps or 100000,  # noqa: SLF001
            "created_at": float(gmx_job._start_timestamp or time.time()),  # noqa: SLF001
            "duration_sec": 30.0,
            "log_line_index": 0,
            "log_total_lines": 500,
        }

    # Rehydrate AMBER jobs from database
    for amber_job in AmberJob.query.all():
        status = JobStatus.TERMINATED.value if amber_job._finish_timestamp else JobStatus.RUNNING.value  # noqa: SLF001
        from models.simulation import Simulation  # noqa: PLC0415

        files = Simulation.get(amber_job.experiment_id, amber_job.simulation_path).resolved_files
        demo_state.mdrun_jobs[amber_job.id] = {
            "status": status,
            "experiment_id": amber_job.experiment_id,
            "prmtop_name": files.get("topology", "md.prmtop"),
            "inpcrd_name": files.get("coordinates", "md.inpcrd"),
            "mdin_name": files.get("control", "md.mdin"),
            "nsteps": amber_job._nsteps or 100000,  # noqa: SLF001
            "created_at": float(amber_job._start_timestamp or time.time()),  # noqa: SLF001
            "duration_sec": 30.0,
            "log_line_index": 0,
            "log_total_lines": 500,
        }

    # Rehydrate tuner jobs from database
    for tuner_job in TunerJob.query.all():
        if tuner_job.is_stopped:
            # Stopped jobs use preserved trials
            demo_state.tuner_jobs[tuner_job.id] = {
                "status": JobStatus.TERMINATED.value,
                "created_at": time.time() - 3600,
                "max_trials": len(tuner_job._preserved_trials or []),  # noqa: SLF001
                "trials": [
                    {
                        "id": t.get("id", f"{tuner_job.id[:10]}-{i:05d}"),
                        "status": t.get("status", JobStatus.TERMINATED.value),
                        "np": t.get("np", 2),
                        "ntomp": t.get("ntomp", 4),
                        "nb": t.get("nb", "cpu"),
                        "pme": t.get("pme", "cpu"),
                        "performance": t.get("performance"),
                    }
                    for i, t in enumerate(tuner_job._preserved_trials or [])  # noqa: SLF001
                ],
            }
        elif tuner_job.error_message:
            # Error jobs are marked as ERROR
            demo_state.tuner_jobs[tuner_job.id] = {
                "status": JobStatus.ERROR.value,
                "created_at": time.time() - 3600,
                "max_trials": 1,
                "trials": [],
            }
        else:
            # Running jobs get simulated trials with TERMINATED, ERROR, RUNNING pattern
            started_at = time.time() - 4
            demo_state.tuner_jobs[tuner_job.id] = {
                "status": JobStatus.RUNNING.value,
                "created_at": started_at,
                "max_trials": 4,
                "trials": [
                    {
                        "id": f"{tuner_job.id[:10]}-00000",
                        "status": JobStatus.TERMINATED.value,
                        "np": 8,
                        "ntomp": 1,
                        "nb": "gpu",
                        "pme": "cpu",
                        "performance": 72.4,
                    },
                    {
                        "id": f"{tuner_job.id[:10]}-00001",
                        "status": JobStatus.ERROR.value,
                        "np": 4,
                        "ntomp": 2,
                        "nb": "cpu",
                        "pme": "cpu",
                        "performance": None,
                    },
                    {
                        "id": f"{tuner_job.id[:10]}-00002",
                        "status": JobStatus.RUNNING.value,
                        "np": 4,
                        "ntomp": 2,
                        "nb": "gpu",
                        "pme": "gpu",
                        "performance": None,
                        "started_at": started_at,
                    },
                ],
            }
