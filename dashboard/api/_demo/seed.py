import time
from datetime import datetime, timedelta

from enums import DeviceType, JobStatus, PodStatus
from extensions import db
from models import Experiment, GromacsJob, Notebook, TunerJob

from .files import ensure_demo_files, write_finished_gmx_log, write_running_gmx_log
from .state import build_model, demo_state


def seed_data() -> None:
    demo_state.notebook_status.clear()
    demo_state.mdrun_jobs.clear()
    demo_state.tuner_jobs.clear()
    demo_state.mdrepo_records.clear()
    demo_state.mdrepo_counter = 1

    if Experiment.query.count() > 0:
        _rehydrate_runtime_state()
        return

    now = datetime.now()

    setup = build_model(
        Experiment,
        id="aaaaa",
        name="Cancer cure",
        source_message="Created by uploading files: cancer_cure.tpr.",
        notebooks_repo="https://github.com/CERIT-SC/mddash-notebooks.git",
        created_at=now - timedelta(days=3),
        updated_at=now - timedelta(days=2),
    )
    setup_notebook = build_model(Notebook, experiment_id=setup.id, token="demo-token-setup")
    demo_state.notebook_status[setup.id] = PodStatus.DOWN

    tuning = build_model(
        Experiment,
        id="bbbbb",
        name="HIV protein behavior research for drug development",
        source_message="Created by downloading repository from 'https://zenodo.org/records/7261108'.",
        notebooks_repo="https://github.com/CERIT-SC/mddash-notebooks.git",
        created_at=now - timedelta(days=2),
        updated_at=now - timedelta(days=1),
    )
    tuning_notebook = build_model(Notebook, experiment_id=tuning.id, token="demo-token-tuning")
    demo_state.notebook_status[tuning.id] = PodStatus.RUNNING

    running_tuner = build_model(
        TunerJob,
        experiment=tuning,
        tpr_name="LSD.tpr",
        id="demo-tuner-lsd",
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
                    "id": "lsd_00000",
                    "status": JobStatus.TERMINATED.value,
                    "np": 8,
                    "ntomp": 1,
                    "nb": "gpu",
                    "pme": "cpu",
                    "performance": 70.158,
                },
                {
                    "id": "lsd_00001",
                    "status": JobStatus.RUNNING.value,
                    "np": 4,
                    "ntomp": 2,
                    "nb": "cpu",
                    "pme": "cpu",
                    "performance": None,
                    "started_at": started_at,
                },
            ],
        }

    stopped_tuner = build_model(
        TunerJob,
        experiment=tuning,
        tpr_name="MDMA.tpr",
        id="demo-tuner-mdma",
        created_at=now - timedelta(hours=9),
        is_stopped=True,
        _preserved_trials=[
            {
                "id": "mdma_00000",
                "status": JobStatus.TERMINATED.value,
                "np": 8,
                "ntomp": 1,
                "nb": "gpu",
                "pme": "cpu",
                "performance": 66.1,
            }
        ],
        error_message=None,
    )

    error_tuner = build_model(
        TunerJob,
        experiment=tuning,
        tpr_name="Failed.tpr",
        id="demo-tuner-failed",
        created_at=now - timedelta(hours=10),
        is_stopped=False,
        error_message="Failed to submit to tuner: Connection timeout",
    )

    running_gmx = build_model(
        GromacsJob,
        id="demo-gmx-running",
        experiment=tuning,
        tpr_name="LSD.tpr",
        pme=DeviceType.CPU,
        nb=DeviceType.CPU,
        np=2,
        ntomp=8,
        extra_args="",
        _nsteps=100000,
        _start_timestamp=int((now - timedelta(hours=3)).timestamp()),
        _finish_timestamp=None,
        _performance=None,
        created_at=now - timedelta(hours=3),
    )
    demo_state.mdrun_jobs[running_gmx.id] = {
        "status": JobStatus.RUNNING.value,
        "experiment_id": tuning.id,
        "tpr_name": "LSD.tpr",
        "nsteps": 100000,
        "created_at": time.time(),
        "duration_sec": 1800,
    }

    finished_gmx = build_model(
        GromacsJob,
        id="demo-gmx-finished",
        experiment=tuning,
        tpr_name="MDMA.tpr",
        pme=DeviceType.CPU,
        nb=DeviceType.GPU,
        np=8,
        ntomp=1,
        extra_args="",
        _nsteps=100000,
        _start_timestamp=int((now - timedelta(days=1)).timestamp()),
        _finish_timestamp=int((now - timedelta(hours=20)).timestamp()),
        _performance=70.158,
        created_at=now - timedelta(days=1),
    )
    demo_state.mdrun_jobs[finished_gmx.id] = {
        "status": JobStatus.TERMINATED.value,
        "experiment_id": tuning.id,
        "tpr_name": "MDMA.tpr",
        "nsteps": 100000,
    }

    published = build_model(
        Experiment,
        id="ccccc",
        name="My first experiment",
        source_message="Created by uploading files: my_first_experiment.tpr.",
        notebooks_repo="https://github.com/CERIT-SC/mddash-notebooks.git",
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
        tpr_name="output.tpr",
        pme=DeviceType.CPU,
        nb=DeviceType.CPU,
        np=4,
        ntomp=4,
        extra_args="",
        _nsteps=50000,
        _start_timestamp=int((now - timedelta(days=9)).timestamp()),
        _finish_timestamp=int((now - timedelta(days=8, hours=20)).timestamp()),
        _performance=45.3,
        created_at=now - timedelta(days=9),
    )
    demo_state.mdrun_jobs[published_gmx.id] = {
        "status": JobStatus.TERMINATED.value,
        "experiment_id": published.id,
        "tpr_name": "output.tpr",
        "nsteps": 50000,
    }

    db.session.add_all(
        [
            setup,
            setup_notebook,
            tuning,
            tuning_notebook,
            running_tuner,
            stopped_tuner,
            error_tuner,
            running_gmx,
            finished_gmx,
            published,
            published_notebook,
            published_gmx,
        ]
    )
    db.session.commit()

    ensure_demo_files(setup.id, ["cancer_cure.tpr", "input.pdb", "trajectory.xtc"])
    ensure_demo_files(tuning.id, ["LSD.tpr", "MDMA.tpr", "Failed.tpr", "input.pdb", "trajectory.xtc"])
    ensure_demo_files(published.id, ["output.tpr", "input.pdb", "trajectory.xtc"])
    write_running_gmx_log(tuning.id, "LSD")
    write_finished_gmx_log(tuning.id, "MDMA", nsteps=100000, performance=70.158)
    write_finished_gmx_log(published.id, "output", nsteps=50000, performance=45.3)


def _rehydrate_runtime_state() -> None:
    tuning = Experiment.query.filter_by(id="bbbbb").first()
    published = Experiment.query.filter_by(id="ccccc").first()
    setup = Experiment.query.filter_by(id="aaaaa").first()

    if setup is not None:
        demo_state.notebook_status[setup.id] = PodStatus.DOWN
        ensure_demo_files(setup.id, ["cancer_cure.tpr", "input.pdb", "trajectory.xtc"])

    if tuning is not None:
        demo_state.notebook_status[tuning.id] = PodStatus.RUNNING
        ensure_demo_files(tuning.id, ["LSD.tpr", "MDMA.tpr", "Failed.tpr", "input.pdb", "trajectory.xtc"])
        write_running_gmx_log(tuning.id, "LSD")
        write_finished_gmx_log(tuning.id, "MDMA", nsteps=100000, performance=70.158)

    if published is not None:
        demo_state.notebook_status[published.id] = PodStatus.DOWN
        ensure_demo_files(published.id, ["output.tpr", "input.pdb", "trajectory.xtc"])
        write_finished_gmx_log(published.id, "output", nsteps=50000, performance=45.3)
        if published.mdrepo_id:
            demo_state.mdrepo_records[published.mdrepo_id] = True
