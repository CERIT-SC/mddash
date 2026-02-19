from __future__ import annotations

import io
import json
import logging
import threading
import time
import zipfile
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from http import HTTPStatus
from pathlib import Path
from typing import TYPE_CHECKING, TypeVar
from uuid import uuid4

import models.experiment as experiment_model
import routes.mdrepo as mdrepo_routes
from clients import caddy, k8s, mdrepo, mdrun, tuner
from config import DATA_DIR, MDREPO_RECORD_NAME, MDREPO_URL
from enums import DeviceType, JobStatus, PodStatus
from extensions import db
from models import Experiment, GromacsJob, Notebook, TunerJob

if TYPE_CHECKING:
    from flask import Flask

logger = logging.getLogger(__name__)

ModelType = TypeVar("ModelType")


@dataclass
class _DemoState:
    initialized: bool = False
    notebook_status: dict[str, PodStatus] = field(default_factory=dict)
    mdrun_jobs: dict[str, str] = field(default_factory=dict)
    tuner_jobs: dict[str, dict] = field(default_factory=dict)
    mdrepo_records: dict[str, bool] = field(default_factory=dict)
    mdrepo_counter: int = 1


demo_state = _DemoState()


def _build_model(model_cls: type[ModelType], **attrs: object) -> ModelType:
    model = model_cls()  # type: ignore[call-arg]
    for attr, value in attrs.items():
        setattr(model, attr, value)
    return model


def setup_demo_profile(app: Flask) -> None:
    """Install demo mocks and seed deterministic local data."""
    if demo_state.initialized:
        return

    _install_mocks()

    app.config["SESSION_COOKIE_SECURE"] = False
    if not app.config.get("SECRET_KEY"):
        app.config["SECRET_KEY"] = "demo-secret"

    with app.app_context():
        _seed_data()

    demo_state.initialized = True
    logger.info("Demo profile initialized with real API routes and mocked integrations.")


def _install_mocks() -> None:
    experiment_model.download_git_repo = _fake_download_git_repo
    experiment_model.requests.get = _fake_experiment_requests_get

    k8s.get_pod_status = _k8s_get_pod_status
    k8s.create_notebook_pod = _k8s_create_notebook_pod
    k8s.delete_pod = _k8s_delete_pod
    k8s.create_service = _k8s_create_service
    k8s.delete_service = _k8s_delete_service
    k8s.get_pod_resource_requests = _k8s_get_pod_resource_requests

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


def _seed_data() -> None:
    if Experiment.query.count() > 0:
        return

    now = datetime.now()

    setup = _build_model(
        Experiment,
        id="aaaaa",
        name="Cancer cure",
        source_message="Created by uploading files: cancer_cure.tpr.",
        notebooks_repo="https://github.com/CERIT-SC/mddash-notebooks.git",
        created_at=now - timedelta(days=3),
        updated_at=now - timedelta(days=2),
    )
    setup_notebook = _build_model(Notebook, experiment_id=setup.id, token="demo-token-setup")
    demo_state.notebook_status[setup.id] = PodStatus.DOWN

    tuning = _build_model(
        Experiment,
        id="bbbbb",
        name="HIV protein behavior research for drug development",
        source_message="Created by downloading repository from 'https://zenodo.org/records/7261108'.",
        notebooks_repo="https://github.com/CERIT-SC/mddash-notebooks.git",
        created_at=now - timedelta(days=2),
        updated_at=now - timedelta(days=1),
    )
    tuning_notebook = _build_model(Notebook, experiment_id=tuning.id, token="demo-token-tuning")
    demo_state.notebook_status[tuning.id] = PodStatus.RUNNING

    running_tuner = _build_model(
        TunerJob,
        experiment=tuning,
        tpr_name="LSD.tpr",
        tuner_run_id="demo-tuner-lsd",
        created_at=now - timedelta(hours=8),
        is_stopped=False,
        error_message=None,
    )
    if running_tuner.tuner_run_id:
        demo_state.tuner_jobs[running_tuner.tuner_run_id] = {
            "status": JobStatus.RUNNING.value,
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
                },
            ],
        }

    stopped_tuner = _build_model(
        TunerJob,
        experiment=tuning,
        tpr_name="MDMA.tpr",
        tuner_run_id="demo-tuner-mdma",
        created_at=now - timedelta(hours=9),
        is_stopped=True,
        _preserved_trials=json.dumps(
            [
                {
                    "id": "mdma_00000",
                    "status": JobStatus.TERMINATED.value,
                    "np": 8,
                    "ntomp": 1,
                    "nb": "gpu",
                    "pme": "cpu",
                    "performance": 66.1,
                }
            ]
        ),
        error_message=None,
    )

    error_tuner = _build_model(
        TunerJob,
        experiment=tuning,
        tpr_name="Failed.tpr",
        tuner_run_id=None,
        created_at=now - timedelta(hours=10),
        is_stopped=False,
        error_message="Failed to submit to tuner: Connection timeout",
    )

    running_gmx = _build_model(
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
    demo_state.mdrun_jobs[running_gmx.id] = JobStatus.RUNNING.value

    finished_gmx = _build_model(
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
    demo_state.mdrun_jobs[finished_gmx.id] = JobStatus.TERMINATED.value

    published = _build_model(
        Experiment,
        id="ccccc",
        name="My first experiment",
        source_message="Created by uploading files: my_first_experiment.tpr.",
        notebooks_repo="https://github.com/CERIT-SC/mddash-notebooks.git",
        mdrepo_id="xej9e-x3720",
        mdrepo_published=True,
        created_at=now - timedelta(days=10),
        updated_at=now - timedelta(days=8),
    )
    published_notebook = _build_model(Notebook, experiment_id=published.id, token="demo-token-published")
    demo_state.notebook_status[published.id] = PodStatus.DOWN
    if published.mdrepo_id:
        demo_state.mdrepo_records[published.mdrepo_id] = True

    published_gmx = _build_model(
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
    demo_state.mdrun_jobs[published_gmx.id] = JobStatus.TERMINATED.value

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

    _ensure_demo_files(setup.id, ["cancer_cure.tpr"])
    _ensure_demo_files(tuning.id, ["LSD.tpr", "MDMA.tpr", "Failed.tpr"])
    _ensure_demo_files(published.id, ["output.tpr"])
    _write_running_gmx_log(tuning.id, "LSD")
    _write_finished_gmx_log(tuning.id, "MDMA", nsteps=100000, performance=70.158)
    _write_finished_gmx_log(published.id, "output", nsteps=50000, performance=45.3)


def _ensure_demo_files(experiment_id: str, filenames: list[str]) -> None:
    experiment_dir = DATA_DIR / experiment_id
    experiment_dir.mkdir(parents=True, exist_ok=True)
    for filename in filenames:
        file_path = experiment_dir / filename
        if not file_path.exists():
            file_path.write_text("demo", encoding="utf-8")


def _write_running_gmx_log(experiment_id: str, deffnm: str) -> None:
    log_path = DATA_DIR / experiment_id / f"{deffnm}.log"
    started = (datetime.now() - timedelta(hours=3)).strftime("%a %b %d %H:%M:%S %Y")
    content = "\n".join(
        [
            f"Started mdrun on {started}",
            "nsteps = 100000",
            "   76543   153.08600",
        ]
    )
    log_path.write_text(content, encoding="utf-8")


def _write_finished_gmx_log(experiment_id: str, deffnm: str, nsteps: int, performance: float) -> None:
    started = (datetime.now() - timedelta(days=1)).strftime("%a %b %d %H:%M:%S %Y")
    finished = (datetime.now() - timedelta(hours=20)).strftime("%a %b %d %H:%M:%S %Y")
    log_path = DATA_DIR / experiment_id / f"{deffnm}.log"
    content = "\n".join(
        [
            f"Started mdrun on {started}",
            f"nsteps = {nsteps}",
            "Finished mdrun on " + finished,
            f"Performance:  {performance}  ns/day",
        ]
    )
    log_path.write_text(content, encoding="utf-8")


def _fake_download_git_repo(repo_url: str, output_dir: Path, access_token: str | None = None) -> None:  # noqa: ARG001
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "README.md").write_text(
        f"Demo notebooks repository mirror for {repo_url}\n",
        encoding="utf-8",
    )


class _SimpleResponse:
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


def _fake_experiment_requests_get(url: str, timeout: int = 30) -> _SimpleResponse:  # noqa: ARG001
    if "files.rcsb.org/download/" in url and url.endswith(".pdb"):
        pdb_content = b"HEADER    DEMO PDB\nATOM      1  N   ALA A   1       0.0   0.0   0.0\nEND\n"
        return _SimpleResponse(200, content=pdb_content)

    if "zenodo.org/api/records/" in url and url.endswith("/files-archive"):
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w") as zf:
            zf.writestr("input.tpr", "demo")
            zf.writestr("README.txt", "demo")
        return _SimpleResponse(200, content=buffer.getvalue())

    return _SimpleResponse(404)


def _fake_mdrepo_requests_get(url: str, headers: dict | None = None, timeout: int = 10) -> _SimpleResponse:  # noqa: ARG001
    token = (headers or {}).get("Authorization", "")
    if url.endswith("/api/me"):
        if token.startswith("Bearer demo"):
            return _SimpleResponse(200, payload={"user": "demo"})
        return _SimpleResponse(401, payload={"message": "Unauthorized"})
    return _SimpleResponse(404)


def _fake_mdrepo_requests_post(url: str, data: dict | None = None, timeout: int = 30) -> _SimpleResponse:  # noqa: ARG001
    if url.endswith("/oauth/token"):
        payload = {
            "access_token": "demo-access-token",
            "refresh_token": "demo-refresh-token",
            "expires_in": 3600,
        }
        return _SimpleResponse(200, payload=payload)
    return _SimpleResponse(404, payload={"message": "Not found"})


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
        "storage": 0,
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
    demo_state.mdrun_jobs[job_id] = JobStatus.RUNNING.value
    _write_running_gmx_log(experiment_id, Path(tpr_name).stem)
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
    status = demo_state.mdrun_jobs.get(job_id, JobStatus.UNKNOWN.value)
    return {
        "id": job_id,
        "status": status,
    }


def _mdrun_delete_job(job_id: str) -> None:
    demo_state.mdrun_jobs.pop(job_id, None)


def _tuner_run_submit(tpr_path: Path, nsteps: int = 25000, extra_args: str = "") -> dict:  # noqa: ARG001
    run_id = f"demo-tuner-{uuid4()}"
    demo_state.tuner_jobs[run_id] = {
        "status": JobStatus.RUNNING.value,
        "trials": [
            {
                "id": f"{run_id[:10]}-00000",
                "status": JobStatus.RUNNING.value,
                "np": 2,
                "ntomp": 4,
                "nb": "cpu",
                "pme": "cpu",
                "performance": None,
            }
        ],
    }
    return {"id": run_id}


def _tuner_poll_status(job_id: str) -> dict:
    status = demo_state.tuner_jobs.get(job_id)
    if status is None:
        return {"status": JobStatus.UNKNOWN.value, "trials": []}
    return status


def _tuner_delete_job(job_id: str) -> dict:
    demo_state.tuner_jobs.pop(job_id, None)
    return {"id": job_id}


def _mdrepo_create_experiment(access_token: str, community: str, metadata: dict) -> dict:  # noqa: ARG001
    record_id = f"demo-{demo_state.mdrepo_counter:05d}"
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
