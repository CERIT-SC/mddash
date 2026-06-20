import logging
from http import HTTPStatus
from typing import TYPE_CHECKING
from uuid import uuid4

from clients import caddy, k8s
from clients.k8s import parse_cpu, parse_memory
from config import GPU_TYPE, MAX_NOTEBOOKS, NAMESPACE, NOTEBOOK_RESOURCES, PREFIX
from enums import NotebookTier, PodStatus
from extensions import db
from kubernetes.client.rest import ApiException
from sqlalchemy.orm import Mapped, mapped_column, relationship
from werkzeug.exceptions import BadRequest, Conflict, Forbidden, InternalServerError

if TYPE_CHECKING:
    from .experiment import Experiment


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


class Notebook(db.Model):  # type: ignore
    """JupyterLab notebook instance for experiment setup."""

    __tablename__ = "notebooks"

    # ID of the notebook inside the database
    id: Mapped[int] = mapped_column(db.Integer, primary_key=True)
    # ID of the experiment this notebook belongs to
    experiment_id: Mapped[str] = mapped_column(db.String(5), db.ForeignKey("experiments.id"))
    # token for accessing jupyter notebook
    token: Mapped[str] = mapped_column(db.String(36), nullable=False, default=lambda: str(uuid4()))
    # resource tier (1x, 2x, 4x) — NULL for notebooks created before tiers were introduced
    tier: Mapped[NotebookTier | None] = mapped_column(
        db.Enum(NotebookTier),
        nullable=True,
    )
    # whether GPU is attached to the notebook container
    gpu: Mapped[bool] = mapped_column(db.Boolean, default=False, server_default=db.text("0"))

    # back-reference to the parent experiment
    experiment: Mapped["Experiment"] = relationship("Experiment", back_populates="notebook")

    @property
    def path(self) -> str:
        """Path to access the notebook via Caddy."""
        return f"{PREFIX}/notebook/{self.experiment_id}/?token={self.token}"

    @property
    def status(self) -> PodStatus:
        """The status of the notebook pod."""
        pod_name = f"notebook-{self.experiment_id}"
        return k8s.get_pod_status(pod_name)

    def start(self, tier: NotebookTier | None = None, gpu: bool = False) -> None:
        """
        Start the notebook pod and service, and create a route in Caddy.

        Args:
            tier: Resource tier for the notebook (1x, 2x, 4x). Defaults to 1x.
            gpu: Whether to attach a GPU to the notebook container.

        Raises:
            BadRequest: If the tier is not a valid NotebookTier value.
            Forbidden: If the resource quota is exceeded when creating the pod.
            Conflict: If the notebook pod already exists.
            InternalServerError: If the pod creation fails or the proxy route cannot be created.
        """
        pod_name = f"notebook-{self.experiment_id}"
        svc_name = f"svc-{self.experiment_id}"

        tier = tier or NotebookTier.SMALL
        if not isinstance(tier, NotebookTier):
            try:
                tier = NotebookTier(tier)
            except ValueError:
                valid = ", ".join(t.value for t in NotebookTier)
                raise BadRequest(description=f"Unknown notebook tier: {tier}. Available: {valid}")

        if gpu and not GPU_TYPE:
            raise BadRequest(description="GPU is not available in this environment.")

        self.tier = tier
        self.gpu = bool(gpu)

        nb_res = get_tier_resources(tier)

        if k8s.count_notebook_pods() >= MAX_NOTEBOOKS:
            raise Forbidden(description=f"Maximum of {MAX_NOTEBOOKS} concurrent notebook(s) reached. Stop one first.")

        nb_cpu = parse_cpu(nb_res["requests"]["cpu"])
        nb_mem = parse_memory(nb_res["requests"]["memory"])
        nb_cpu_limit = parse_cpu(nb_res["limits"]["cpu"])
        nb_mem_limit = parse_memory(nb_res["limits"]["memory"])
        if msg := k8s.check_quota_headroom(nb_cpu, nb_mem, nb_cpu_limit, nb_mem_limit):
            raise Forbidden(description=msg)

        try:
            k8s.create_notebook_pod(
                pod_name,
                self.experiment_id,
                f"{PREFIX}/notebook/{self.experiment_id}",
                self.token,
                notebook_resources=nb_res,
                gpu=self.gpu,
                tier=tier,
            )
        except ApiException as e:
            if e.status == HTTPStatus.FORBIDDEN:
                logger.debug("Quota exceeded when creating notebook pod.", exc_info=True)
                raise Forbidden(description="Resource quota exceeded. Please stop other notebooks.")
            if e.status == HTTPStatus.CONFLICT:
                raise Conflict(description="Notebook pod already exists.")

            logger.exception("Failed to create notebook pod.")
            raise InternalServerError(description=f"Failed to create notebook pod: {e.reason}")

        try:
            k8s.create_service(svc_name, pod_name)
        except Exception:
            k8s.delete_pod(pod_name)
            raise

        route_id = caddy.add_proxy_route(
            path=f"{PREFIX}/notebook/{self.experiment_id}",
            upstream=f"{svc_name}.{NAMESPACE}.svc.cluster.local:80",
            route_id=f"route-{self.experiment_id}-notebook",
        )

        if route_id is None:
            k8s.delete_pod(pod_name)
            k8s.delete_service(svc_name)
            raise InternalServerError(description="Failed to create proxy connection to notebook.")

    def stop(self) -> None:
        """Stop the notebook pod and service, and remove the route from Caddy."""
        if self.status == PodStatus.UNKNOWN:
            logger.warning(f"Notebook {self.experiment_id} status unknown. No action taken.")
            return

        pod_name = f"notebook-{self.experiment_id}"
        svc_name = f"svc-{self.experiment_id}"
        route_id = f"route-{self.experiment_id}-notebook"

        try:
            k8s.delete_pod(pod_name)  # noop if pod already gone (e.g. idle-culled)
        except Exception:
            logger.exception("Failed to delete notebook pod.")

        try:
            k8s.delete_service(svc_name)
        except Exception:
            logger.exception("Failed to delete notebook service.")

        if not caddy.remove_route(route_id):
            logger.error("Failed to remove route from Caddy.")
