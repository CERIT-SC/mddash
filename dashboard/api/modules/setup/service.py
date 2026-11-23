"""
Headless setup runs: the setup notebook executed by a Kubernetes Job in the notebook image.

No DB table. The Job is the liveness signal and the executor's status doc the durable record.
"""

import logging
from dataclasses import dataclass
from datetime import UTC, datetime
from http import HTTPStatus
from pathlib import PurePosixPath
from typing import Annotated, Any

import anyio
from clients.k8s import is_api_exception, parse_cpu, parse_memory
from core.config import DATA_DIR, GPU_PRODUCT, GPU_TYPE, NOTEBOOK_IMAGE
from core.dependencies import ClientsDep
from core.enums import NotebookTier
from core.errors import ApiError, BadRequest, Forbidden, NotFound
from core.validators import check_path
from core.worker_jobs import (
    DELETION_TIMEOUT,
    delete_worker_job,
    dns1123_name,
    read_status_doc,
    worker_job_manifest,
    write_status_doc,
)
from fastapi import Depends

from modules.experiments.models import Experiment
from modules.notebooks.tiers import get_tier_resources
from modules.setup.schemas import SetupRun, SetupRunError, SetupState
from modules.simulations.manifest import Simulation

logger = logging.getLogger(__name__)

SETUP_APP_LABEL = "setup-run"
STATUS_PREFIX = ".mddash-setup-run."
_IMAGE_PULL_REASONS = {"ErrImagePull", "ImagePullBackOff", "InvalidImageName"}
_RETRY = "Run setup again. If it keeps failing, contact support."


def job_name(experiment_id: str, notebook: str) -> str:
    """One Job per experiment and notebook, so a second start while one runs collides."""
    return dns1123_name("setup", experiment_id, notebook, fallback_prefix="setup")


def status_path(notebook: str) -> str:
    """Experiment-relative status doc, hidden next to the notebook."""
    path = PurePosixPath(notebook)
    return str(path.with_name(f"{STATUS_PREFIX}{path.name}.json"))


@dataclass(frozen=True)
class JobView:
    """What the reconciliation needs from the Job and its pod."""

    live: bool
    failed: bool = False
    waiting: bool = False
    infra_error: SetupRunError | None = None


def _condition(obj: Any, kind: str) -> Any:  # ruff:ignore[any-type]
    conditions = getattr(getattr(obj, "status", None), "conditions", None) or []
    return next(
        (c for c in conditions if getattr(c, "type", None) == kind and getattr(c, "status", None) == "True"), None
    )


def _pod_view(pods: list[Any]) -> tuple[bool, SetupRunError | None]:
    """(unschedulable, infrastructure error) read from the Job's pod."""
    for pod in pods:
        status = getattr(pod, "status", None)
        for condition in getattr(status, "conditions", None) or []:
            if condition.type == "PodScheduled" and condition.status == "False" and condition.reason == "Unschedulable":
                return True, None
        for container in getattr(status, "container_statuses", None) or []:
            state = container.state
            if state and state.waiting and state.waiting.reason in _IMAGE_PULL_REASONS:
                return False, SetupRunError(message="The setup environment could not be downloaded.", solution=_RETRY)
            terminated = (state and state.terminated) or (container.last_state and container.last_state.terminated)
            if terminated and terminated.reason == "OOMKilled":
                return False, SetupRunError(
                    message="Setup ran out of memory.", solution="Run setup again with a larger size under Expert."
                )
    return False, None


def reconcile(notebook: str, job: JobView | None, doc: dict | None, has_valid_manifest: bool) -> SetupRun | None:
    """Combine the Job and the status doc into one run state; None when setup never ran."""
    if job is None and doc is None:
        return None
    progress: dict[str, Any] = {
        "notebook": notebook,
        "step": (doc or {}).get("step") or 0,
        "total": (doc or {}).get("total"),
        "title": (doc or {}).get("title"),
        "manifests": (doc or {}).get("manifests") or [],
        "started_at": (doc or {}).get("started_at"),
        "finished_at": (doc or {}).get("finished_at"),
    }
    state = (doc or {}).get("state")

    if state == SetupState.STOPPED:
        return SetupRun(state=SetupState.STOPPED, **progress)
    if state == "failed":
        error = doc.get("error") or {} if doc else {}
        ename, evalue = error.get("ename") or "Error", error.get("evalue") or ""
        return SetupRun(
            state=SetupState.FAILED,
            error=SetupRunError(
                step=error.get("step"), title=progress["title"], message=f"{ename}: {evalue}" if evalue else ename
            ),
            **progress,
        )
    if state == "done":
        if has_valid_manifest:
            return SetupRun(state=SetupState.DONE, **progress)
        return SetupRun(
            state=SetupState.FAILED,
            error=SetupRunError(
                message="Setup finished without writing a simulation manifest.",
                solution="Open the notebook to check its last steps.",
            ),
            **progress,
        )

    # The doc says running (or there is none yet): the Job decides.
    if job is not None and job.infra_error is not None:
        return SetupRun(state=SetupState.FAILED, error=job.infra_error, **progress)
    if job is not None and job.live:
        if state is None:
            return SetupRun(state=SetupState.STARTING, waiting=job.waiting, **progress)
        return SetupRun(state=SetupState.RUNNING, **progress)
    message = "Setup stopped unexpectedly." if job is not None and job.failed else "Setup was interrupted."
    return SetupRun(state=SetupState.FAILED, error=SetupRunError(message=message, solution=_RETRY), **progress)


class SetupService:
    """Start, observe, and stop headless setup runs."""

    def __init__(self, clients: ClientsDep) -> None:
        """Bind to the Kubernetes client."""
        self._k8s = clients.k8s

    @staticmethod
    def resolve_notebook(experiment: Experiment, notebook: str) -> str:
        """
        Normalize the notebook path and require it to exist.

        Raises:
            BadRequest: If the path is unsafe or not a notebook.
            NotFound: If the notebook does not exist.
        """
        notebook = PurePosixPath(notebook).as_posix()
        check_path(notebook, DATA_DIR / experiment.id)
        if not notebook.endswith(".ipynb"):
            raise BadRequest("Setup runs a notebook ('.ipynb').")
        if not (DATA_DIR / experiment.id / notebook).is_file():
            raise NotFound(f"Notebook '{notebook}' not found.")
        return notebook

    async def _job_view(self, name: str) -> JobView | None:
        job = await self._k8s.read_job(name)
        if job is None:
            return None
        if _condition(job, "Complete"):
            return JobView(live=False)
        failed = _condition(job, "Failed") is not None
        waiting, infra_error = _pod_view(await self._k8s.list_pods_by_label(f"job-name={name}"))
        if failed and infra_error is None and getattr(_condition(job, "Failed"), "reason", None) == "DeadlineExceeded":
            infra_error = SetupRunError(message="Setup took longer than 24 hours and was stopped.", solution=_RETRY)
        return JobView(live=not failed, failed=failed, waiting=waiting, infra_error=infra_error)

    async def get(self, experiment: Experiment, notebook: str) -> SetupRun:
        """
        Get the notebook's setup run.

        Raises:
            NotFound: If setup never ran for this notebook.
        """
        job = await self._job_view(job_name(experiment.id, notebook))
        doc = await anyio.to_thread.run_sync(read_status_doc, DATA_DIR / experiment.id / status_path(notebook))
        manifests = (doc or {}).get("manifests") or []
        has_valid = any(_is_valid_manifest(experiment, path) for path in manifests if isinstance(path, str))
        run = reconcile(notebook, job, doc, has_valid)
        if run is None:
            raise NotFound(f"Setup has not run for '{notebook}'.")
        return run

    async def start(self, experiment: Experiment, notebook: str, tier: NotebookTier | None, gpu: bool) -> SetupRun:
        """
        Submit the setup Job.

        Raises:
            ApiError: If a run is in progress (409), GPU is unavailable, or the Job is refused.
            Forbidden: If the namespace quota has no room.
        """
        name = job_name(experiment.id, notebook)
        current = await self._job_view(name)
        if current is not None and current.live:
            raise ApiError(
                HTTPStatus.CONFLICT,
                "Setup is already running for this notebook.",
                "urn:mddash:setup-running",
                "Wait for it to finish or stop it first.",
            )
        if gpu and not GPU_TYPE:
            raise ApiError(
                HTTPStatus.BAD_REQUEST,
                "GPU is not available in this environment.",
                "urn:mddash:gpu-unavailable",
                "GPU acceleration isn't enabled here; run setup without GPU.",
            )

        resources = get_tier_resources(tier or NotebookTier.SMALL)
        requests, limits = resources["requests"], resources["limits"]
        if msg := await self._k8s.check_quota_headroom(
            parse_cpu(requests["cpu"]),
            parse_memory(requests["memory"]),
            parse_cpu(limits["cpu"]),
            parse_memory(limits["memory"]),
        ):
            raise Forbidden(msg)

        if current is not None and not await delete_worker_job(self._k8s, name):
            raise ApiError(
                HTTPStatus.CONFLICT,
                "The previous setup run is still shutting down.",
                "urn:mddash:setup-running",
                f"Try again in {DELETION_TIMEOUT} seconds.",
            )
        doc_path = DATA_DIR / experiment.id / status_path(notebook)
        await anyio.to_thread.run_sync(lambda: doc_path.unlink(missing_ok=True))

        try:
            await self._k8s.create_job_raw(_job_manifest(name, experiment.id, notebook, resources, gpu))
        except Exception as e:
            if is_api_exception(e, HTTPStatus.FORBIDDEN):
                raise Forbidden("Resource quota exceeded. Stop a notebook or another run first.") from e
            raise
        logger.info("Setup Job %s submitted for %s/%s", name, experiment.id, notebook)
        return SetupRun(notebook=notebook, state=SetupState.STARTING)

    async def stop(self, experiment: Experiment, notebook: str) -> None:
        """
        Stop the run: delete the Job and mark the doc stopped.

        Raises:
            NotFound: If no setup run is in progress.
        """
        run = await self.get(experiment, notebook)
        if run.state not in {SetupState.STARTING, SetupState.RUNNING}:
            raise NotFound(f"No setup run is in progress for '{notebook}'.")
        await delete_worker_job(self._k8s, job_name(experiment.id, notebook))
        doc = run.model_dump(mode="json", include={"step", "total", "title", "started_at", "manifests"})
        doc |= {"state": SetupState.STOPPED.value, "finished_at": datetime.now(UTC).isoformat()}
        await anyio.to_thread.run_sync(write_status_doc, DATA_DIR / experiment.id / status_path(notebook), doc)


def _is_valid_manifest(experiment: Experiment, path: str) -> bool:
    try:
        return Simulation.get(experiment.id, path, experiment).valid
    except ApiError:
        return False


def _job_manifest(name: str, experiment_id: str, notebook: str, resources: dict, gpu: bool) -> dict[str, Any]:
    workdir = f"/mddash/{experiment_id}"
    manifest = worker_job_manifest(
        name=name,
        app=SETUP_APP_LABEL,
        experiment_id=experiment_id,
        container="setup",
        image=NOTEBOOK_IMAGE,
        # start.sh runs before-notebook.d (Binder install) as JupyterLab's pod does.
        command=["start.sh", "run-setup.sh"],
        args=[notebook, "--status", status_path(notebook)],
        env=[
            {"name": "WORKDIR", "value": workdir},
            {"name": "JUPYTER_DOCKER_STACKS_QUIET", "value": "1"},
            {"name": "JUPYTER_PATH", "value": f"{workdir}/.binder-env/share/jupyter:/opt/conda/share/jupyter"},
        ],
    )
    pod = manifest["spec"]["template"]["spec"]
    container = pod["containers"][0]
    container["workingDir"] = workdir
    container["resources"] = {kind: dict(values) for kind, values in resources.items()}
    if gpu and GPU_TYPE:
        container["resources"].setdefault("requests", {})[GPU_TYPE] = "1"
        container["resources"].setdefault("limits", {})[GPU_TYPE] = "1"
        if GPU_PRODUCT:
            pod["nodeSelector"] = {"nvidia.com/gpu.product": GPU_PRODUCT}
    return manifest


SetupServiceDep = Annotated[SetupService, Depends()]
