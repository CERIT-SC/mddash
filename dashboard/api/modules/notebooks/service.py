"""Notebook pods: status, start (pod, service, Caddy route), and stop."""

import logging
from http import HTTPStatus
from typing import Annotated

from clients.k8s import is_api_exception, parse_cpu, parse_memory
from core.config import GPU_TYPE, MAX_NOTEBOOKS, NAMESPACE, PREFIX
from core.dependencies import ClientsDep
from core.enums import NotebookTier, PodStatus
from core.errors import ApiError, Conflict, Forbidden, InternalServerError
from fastapi import Depends

from modules.notebooks.models import Notebook
from modules.notebooks.tiers import get_tier_resources

logger = logging.getLogger(__name__)


class NotebookService:
    """Remote state and lifecycle of experiment notebooks."""

    def __init__(self, clients: ClientsDep) -> None:
        """Bind to the Kubernetes and Caddy clients."""
        self._k8s = clients.k8s
        self._caddy = clients.caddy

    async def refresh(self, notebook: Notebook) -> None:
        """Read the pod's status and start time."""
        notebook.record_pod(await self._k8s.get_pod_info(notebook.pod_name))

    async def start(self, notebook: Notebook, tier: NotebookTier | None = None, gpu: bool = False) -> None:
        """
        Start the notebook pod and service, and create a route in Caddy (the caller commits tier/gpu).

        Args:
            notebook: The notebook to start.
            tier: Resource tier for the notebook (1x, 2x, 4x). Defaults to 1x.
            gpu: Whether to attach a GPU to the notebook container.

        Raises:
            Conflict: If the experiment is archived; its files only exist in S3 until restored.
            Forbidden: If the resource quota is exceeded when creating the pod.
            InternalServerError: If the pod creation fails or the proxy route cannot be created.
        """
        if notebook.experiment and notebook.experiment.archived_at is not None:
            raise Conflict("Experiment is archived. Restore it before starting the notebook.")

        experiment_id = notebook.experiment_id
        pod_name = notebook.pod_name
        svc_name = f"svc-{experiment_id}"
        tier = tier or NotebookTier.SMALL

        if gpu and not GPU_TYPE:
            raise ApiError(
                HTTPStatus.BAD_REQUEST,
                "GPU is not available in this environment.",
                "urn:mddash:gpu-unavailable",
                "GPU acceleration isn't enabled here; start the notebook without GPU.",
            )

        notebook.tier = tier
        notebook.gpu = bool(gpu)

        nb_res = get_tier_resources(tier)

        if await self._k8s.count_notebook_pods() >= MAX_NOTEBOOKS:
            raise ApiError(
                HTTPStatus.FORBIDDEN,
                f"Maximum of {MAX_NOTEBOOKS} concurrent notebook(s) reached. Stop one first.",
                "urn:mddash:notebook-quota-exceeded",
                "Stop another notebook first, then start this one.",
            )

        nb_cpu = parse_cpu(nb_res["requests"]["cpu"])
        nb_mem = parse_memory(nb_res["requests"]["memory"])
        nb_cpu_limit = parse_cpu(nb_res["limits"]["cpu"])
        nb_mem_limit = parse_memory(nb_res["limits"]["memory"])
        if msg := await self._k8s.check_quota_headroom(nb_cpu, nb_mem, nb_cpu_limit, nb_mem_limit):
            raise Forbidden(msg)

        try:
            pod_uid = await self._k8s.create_notebook_pod(
                pod_name,
                experiment_id,
                f"{PREFIX}/notebook/{experiment_id}",
                notebook.token,
                notebook_resources=nb_res,
                gpu=notebook.gpu,
                tier=tier,
            )
        except Exception as e:
            if is_api_exception(e, HTTPStatus.FORBIDDEN):
                logger.debug("Quota exceeded when creating notebook pod.", exc_info=True)
                raise Forbidden("Resource quota exceeded. Please stop other notebooks.")
            if is_api_exception(e, HTTPStatus.CONFLICT):
                raise ApiError(
                    HTTPStatus.CONFLICT,
                    "Notebook pod already exists.",
                    "urn:mddash:notebook-already-exists",
                    "The notebook is already running; open it instead of starting a new one.",
                )
            if is_api_exception(e):
                raise InternalServerError("Failed to create notebook pod.") from e
            raise

        try:
            await self._k8s.create_service(svc_name, pod_name, pod_uid)
        except Exception:
            await self._k8s.delete_pod(pod_name)
            raise

        route_id = await self._caddy.add_proxy_route(
            path=f"{PREFIX}/notebook/{experiment_id}",
            upstream=f"{svc_name}.{NAMESPACE}.svc.cluster.local:80",
            route_id=f"route-{experiment_id}-notebook",
        )

        if route_id is None:
            await self._k8s.delete_pod(pod_name)
            await self._k8s.delete_service(svc_name)
            raise InternalServerError("Failed to create proxy connection to notebook.")

        await self.refresh(notebook)

    async def stop(self, notebook: Notebook) -> None:
        """Stop the notebook pod and service, and remove the route from Caddy."""
        if not notebook.refreshed:
            await self.refresh(notebook)
        if notebook.status == PodStatus.UNKNOWN:
            logger.warning(f"Notebook {notebook.experiment_id} status unknown. No action taken.")
            return

        svc_name = f"svc-{notebook.experiment_id}"
        route_id = f"route-{notebook.experiment_id}-notebook"

        try:
            await self._k8s.delete_pod(notebook.pod_name)  # noop if pod already gone (e.g. idle-culled)
        except Exception:
            logger.exception("Failed to delete notebook pod.")

        try:
            await self._k8s.delete_service(svc_name)
        except Exception:
            logger.exception("Failed to delete notebook service.")

        if not await self._caddy.remove_route(route_id):
            logger.error("Failed to remove route from Caddy.")

    async def stop_if_running(self, notebook: Notebook | None) -> None:
        """Stop a running notebook (deleting or archiving freezes the files under it)."""
        if notebook is None:
            return
        await self.refresh(notebook)
        if notebook.status == PodStatus.RUNNING:
            await self.stop(notebook)


NotebookServiceDep = Annotated[NotebookService, Depends()]
