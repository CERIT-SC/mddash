import logging
from http import HTTPStatus
from typing import TYPE_CHECKING
from uuid import uuid4

import sqlalchemy as sa
from clients import caddy, k8s
from clients.k8s import parse_cpu, parse_memory
from core.config import GPU_TYPE, MAX_NOTEBOOKS, NAMESPACE, NOTEBOOK_RESOURCES, PREFIX
from core.db import Base
from core.enums import NotebookTier, PodStatus
from core.errors import ApiError, Conflict, Forbidden, InternalServerError
from sqlalchemy.orm import Mapped, mapped_column, relationship

if TYPE_CHECKING:
    from datetime import datetime

    from modules.experiments.models import Experiment


logger = logging.getLogger(__name__)


def _multiply_resource(value: str, factor: int) -> str:
    if not value:
        return value
    value = value.strip()
    if value.endswith("m"):
        return f"{int(value[:-1]) * factor}m"
    if value.endswith("Gi") or value.endswith("Mi"):
        # Use parse_memory to avoid int() truncating fractional Gi/Mi values
        bytes_val = parse_memory(value) * factor
        if bytes_val % (1024**3) == 0:
            return f"{bytes_val // (1024**3)}Gi"
        return f"{bytes_val // (1024**2)}Mi"
    # Plain number (CPU cores)
    return str(float(value) * factor)


def get_tier_resources(tier: NotebookTier) -> dict:
    """
    Return notebook_resources scaled by the tier multiplier.

    The base values come from the NOTEBOOK_RESOURCES env vars (1x tier).
    Higher tiers multiply all CPU and memory values by the tier factor.

    Returns:
        A notebook_resources dict with CPU/memory scaled by the tier factor.
    """
    factor = tier.multiplier
    if factor == 1:
        return NOTEBOOK_RESOURCES

    def scale(res: dict[str, dict[str, str]]) -> dict[str, dict[str, str]]:
        return {
            category: {key: _multiply_resource(val, factor) for key, val in values.items()}
            for category, values in res.items()
        }

    return scale(NOTEBOOK_RESOURCES)


class Notebook(Base):
    """JupyterLab notebook instance for experiment setup."""

    __tablename__ = "notebooks"

    # ID of the notebook inside the database
    id: Mapped[int] = mapped_column(sa.Integer, primary_key=True)
    # ID of the experiment this notebook belongs to
    experiment_id: Mapped[str] = mapped_column(sa.String(5), sa.ForeignKey("experiments.id"))
    # token for accessing jupyter notebook
    token: Mapped[str] = mapped_column(sa.String(36), nullable=False, default=lambda: str(uuid4()))
    # resource tier (1x, 2x, 4x); NULL for notebooks created before tiers were introduced
    tier: Mapped[NotebookTier | None] = mapped_column(sa.Enum(NotebookTier), nullable=True)
    # whether GPU is attached to the notebook container
    gpu: Mapped[bool] = mapped_column(sa.Boolean, default=False, server_default=sa.text("0"))

    # back-reference to the parent experiment
    # Never lazy-loads (async); notebooks are always reached through their experiment.
    experiment: Mapped["Experiment"] = relationship("Experiment", back_populates="notebook", lazy="raise_on_sql")

    # Transient: (status, start time) from one K8s read by refresh()
    _pod_info: "tuple[PodStatus, datetime | None] | None" = None

    @property
    def _pod_name(self) -> str:
        return f"notebook-{self.experiment_id}"

    @property
    def path(self) -> str:
        """Path to access the notebook via Caddy."""
        return f"{PREFIX}/notebook/{self.experiment_id}/?token={self.token}"

    async def refresh(self) -> None:
        """Read the pod's status and start time."""
        self._pod_info = await k8s.get_pod_info(self._pod_name)

    def _pod(self) -> "tuple[PodStatus, datetime | None]":
        if self._pod_info is None:
            raise RuntimeError(f"Notebook {self.experiment_id} pod read before refresh()")
        return self._pod_info

    @property
    def status(self) -> PodStatus:
        """The status of the notebook pod."""
        return self._pod()[0]

    @property
    def started_at(self) -> "datetime | None":
        """When the notebook pod was started (None while the pod is absent)."""
        return self._pod()[1]

    async def start(self, tier: NotebookTier | None = None, gpu: bool = False) -> None:
        """
        Start the notebook pod and service, and create a route in Caddy (the caller commits tier/gpu).

        Args:
            tier: Resource tier for the notebook (1x, 2x, 4x). Defaults to 1x.
            gpu: Whether to attach a GPU to the notebook container.

        Raises:
            Conflict: If the experiment is archived; its files only exist in S3 until restored.
            Forbidden: If the resource quota is exceeded when creating the pod.
            InternalServerError: If the pod creation fails or the proxy route cannot be created.
        """
        if self.experiment and self.experiment.archived_at is not None:
            raise Conflict("Experiment is archived. Restore it before starting the notebook.")

        pod_name = self._pod_name
        svc_name = f"svc-{self.experiment_id}"
        tier = tier or NotebookTier.SMALL

        if gpu and not GPU_TYPE:
            raise ApiError(
                HTTPStatus.BAD_REQUEST,
                "GPU is not available in this environment.",
                "urn:mddash:gpu-unavailable",
                "GPU acceleration isn't enabled here; start the notebook without GPU.",
            )

        self.tier = tier
        self.gpu = bool(gpu)

        nb_res = get_tier_resources(tier)

        if await k8s.count_notebook_pods() >= MAX_NOTEBOOKS:
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
        if msg := await k8s.check_quota_headroom(nb_cpu, nb_mem, nb_cpu_limit, nb_mem_limit):
            raise Forbidden(msg)

        try:
            pod_uid = await k8s.create_notebook_pod(
                pod_name,
                self.experiment_id,
                f"{PREFIX}/notebook/{self.experiment_id}",
                self.token,
                notebook_resources=nb_res,
                gpu=self.gpu,
                tier=tier,
            )
        except Exception as e:
            if k8s.is_api_exception(e, HTTPStatus.FORBIDDEN):
                logger.debug("Quota exceeded when creating notebook pod.", exc_info=True)
                raise Forbidden("Resource quota exceeded. Please stop other notebooks.")
            if k8s.is_api_exception(e, HTTPStatus.CONFLICT):
                raise ApiError(
                    HTTPStatus.CONFLICT,
                    "Notebook pod already exists.",
                    "urn:mddash:notebook-already-exists",
                    "The notebook is already running; open it instead of starting a new one.",
                )
            if k8s.is_api_exception(e):
                raise InternalServerError("Failed to create notebook pod.") from e
            raise

        try:
            await k8s.create_service(svc_name, pod_name, pod_uid)
        except Exception:
            await k8s.delete_pod(pod_name)
            raise

        route_id = await caddy.add_proxy_route(
            path=f"{PREFIX}/notebook/{self.experiment_id}",
            upstream=f"{svc_name}.{NAMESPACE}.svc.cluster.local:80",
            route_id=f"route-{self.experiment_id}-notebook",
        )

        if route_id is None:
            await k8s.delete_pod(pod_name)
            await k8s.delete_service(svc_name)
            raise InternalServerError("Failed to create proxy connection to notebook.")

        await self.refresh()

    async def stop(self) -> None:
        """Stop the notebook pod and service, and remove the route from Caddy."""
        if self._pod_info is None:
            await self.refresh()
        if self.status == PodStatus.UNKNOWN:
            logger.warning(f"Notebook {self.experiment_id} status unknown. No action taken.")
            return

        svc_name = f"svc-{self.experiment_id}"
        route_id = f"route-{self.experiment_id}-notebook"

        try:
            await k8s.delete_pod(self._pod_name)  # noop if pod already gone (e.g. idle-culled)
        except Exception:
            logger.exception("Failed to delete notebook pod.")

        try:
            await k8s.delete_service(svc_name)
        except Exception:
            logger.exception("Failed to delete notebook service.")

        if not await caddy.remove_route(route_id):
            logger.error("Failed to remove route from Caddy.")
