from __future__ import annotations

import asyncio
import logging
import time
from http import HTTPStatus
from typing import TYPE_CHECKING, Any, cast

from core.config import (
    CPU_LIMIT_QUOTA,
    CPU_REQUEST_QUOTA,
    GPU_TYPE,
    IMAGE_PULL_POLICY,
    MEMORY_LIMIT_QUOTA,
    MEMORY_REQUEST_QUOTA,
    NAMESPACE,
    NOTEBOOK_IDLE_TIMEOUT,
    NOTEBOOK_IMAGE,
    PVC_NAME,
)
from core.enums import JobStatus, PodStatus

if TYPE_CHECKING:
    from datetime import datetime

    from core.enums import NotebookTier

    # Available at runtime via _load_k8s() populating module globals.
    from kubernetes_asyncio.client import (  # ruff:ignore[runtime-import-in-type-checking-block]
        ApiClient,
        BatchV1Api,
        CoreV1Api,
        V1DeleteOptions,
        V1ObjectMeta,
        V1OwnerReference,
        V1Service,
        V1ServicePort,
        V1ServiceSpec,
    )
    from kubernetes_asyncio.client.exceptions import ApiException  # ruff:ignore[runtime-import-in-type-checking-block]

logger = logging.getLogger(__name__)

_k8s_loaded = False


def _load_k8s() -> None:
    """Import kubernetes_asyncio symbols into module globals on first k8s use (the import is slow)."""
    global _k8s_loaded  # ruff:ignore[global-statement]
    if _k8s_loaded:
        return
    from kubernetes_asyncio.client import (  # ruff:ignore[import-outside-top-level]
        ApiClient,
        BatchV1Api,
        CoreV1Api,
        V1DeleteOptions,
        V1ObjectMeta,
        V1OwnerReference,
        V1Service,
        V1ServicePort,
        V1ServiceSpec,
    )
    from kubernetes_asyncio.client.exceptions import ApiException  # ruff:ignore[import-outside-top-level]

    globals().update(
        ApiClient=ApiClient,
        BatchV1Api=BatchV1Api,
        CoreV1Api=CoreV1Api,
        V1DeleteOptions=V1DeleteOptions,
        V1ObjectMeta=V1ObjectMeta,
        V1OwnerReference=V1OwnerReference,
        V1Service=V1Service,
        V1ServicePort=V1ServicePort,
        V1ServiceSpec=V1ServiceSpec,
        ApiException=ApiException,
    )
    _k8s_loaded = True


def is_api_exception(exc: BaseException, status: int | None = None) -> bool:
    """Whether `exc` is a Kubernetes ApiException (optionally with a given HTTP status)."""
    _load_k8s()
    return isinstance(exc, ApiException) and (status is None or exc.status == status)


def get_container(
    name: str,
    image: str,
    experiment_id: str,
    volume_name: str,
    command: list[str],
    env: list[dict] | None = None,
    set_working_dir: bool = True,
    resources: dict | None = None,
) -> dict:
    """
    Container spec with the e-INFRA security context and the shared volume at /mddash.

    Args:
        name: The name of the container.
        image: The container image to use.
        experiment_id: The ID of the experiment, used to set the working directory.
        volume_name: The name of the volume to mount at /mddash.
        command: The command to run in the container.
        env: Optional list of environment variable dictionaries with 'name' and 'value' keys.
        set_working_dir: Whether to set the working directory to /mddash/{experiment_id}.
        resources: Optional resource requests/limits dict.
    """
    container: dict[str, Any] = {
        "securityContext": {
            "runAsUser": 1000,
            "runAsGroup": 1000,
            "runAsNonRoot": True,
            "allowPrivilegeEscalation": False,
            "capabilities": {"drop": ["ALL"]},
            "seccompProfile": {"type": "RuntimeDefault"},
        },
        "name": name,
        "image": image,
        "imagePullPolicy": IMAGE_PULL_POLICY,
        "resources": resources
        or {"requests": {"cpu": "50m", "memory": "64Mi"}, "limits": {"cpu": "500m", "memory": "256Mi"}},
        "command": command,
        "volumeMounts": [{"mountPath": "/mddash", "name": volume_name}],
    }

    if set_working_dir:
        container["workingDir"] = f"/mddash/{experiment_id}"

    if env:
        container["env"] = env

    return container


def parse_cpu(cpu_str: str | None) -> int:
    """CPU value in Kubernetes format (`100m`, `1`, `1.5`) to millicores."""
    if not cpu_str:
        return 0

    cpu_str = str(cpu_str)
    if cpu_str.endswith("m"):
        return int(cpu_str[:-1])
    return int(float(cpu_str) * 1000)


def parse_memory(mem_str: str | None) -> int:
    """Memory value in Kubernetes format (`128Mi`, `1Gi`, `1G`) to bytes."""
    if not mem_str:
        return 0

    mem_str = str(mem_str).strip()
    if not mem_str:
        return 0

    if mem_str.endswith("Gi"):
        return int(float(mem_str[:-2]) * 1024**3)
    if mem_str.endswith("G"):
        return int(float(mem_str[:-1]) * 1000**3)
    if mem_str.endswith("Mi"):
        return int(float(mem_str[:-2]) * 1024**2)
    if mem_str.endswith("M"):
        return int(float(mem_str[:-1]) * 1000**2)
    if mem_str.endswith("Ki"):
        return int(float(mem_str[:-2]) * 1024)
    if mem_str.endswith("K"):
        return int(float(mem_str[:-1]) * 1000)
    if mem_str.endswith("Ti"):
        return int(float(mem_str[:-2]) * 1024**4)
    if mem_str.endswith("T"):
        return int(float(mem_str[:-1]) * 1000**4)

    # Plain number (bytes)
    try:
        return int(float(mem_str))
    except (ValueError, TypeError):
        logger.warning(f"Unable to parse memory value: {mem_str}")
        return 0


def _sum_container_resources(containers: list, resource_type: str) -> dict:
    """Sum CPU (millicores) and memory (bytes) of `requests` or `limits` over containers."""
    total_cpu = 0
    total_memory = 0

    for container in containers:
        if not hasattr(container, "resources") or container.resources is None:
            continue

        resources = getattr(container.resources, resource_type, None)
        if not resources:
            continue

        cpu_value = resources.get("cpu") if isinstance(resources, dict) else None
        memory_value = resources.get("memory") if isinstance(resources, dict) else None

        total_cpu += parse_cpu(cpu_value)
        total_memory += parse_memory(memory_value)

    return {"cpu": total_cpu, "memory": total_memory}


class K8sClient:  # ruff:ignore[too-many-public-methods]
    """Kubernetes API access for the user namespace; in-cluster config loads on first use."""

    def __init__(self, core_v1: CoreV1Api | None = None, batch_v1: BatchV1Api | None = None) -> None:
        """Use the given API clients (tests) or build them from the in-cluster config on first use."""
        self._api_client: ApiClient | None = None
        self._core_v1 = core_v1
        self._batch_v1 = batch_v1

    def _get_api_client(self) -> ApiClient:
        if self._api_client is None:
            _load_k8s()
            from kubernetes_asyncio import config  # ruff:ignore[import-outside-top-level]

            config.load_incluster_config()
            self._api_client = ApiClient()
        return self._api_client

    @property
    def core_v1(self) -> CoreV1Api:
        """CoreV1Api client, created on first use."""
        _load_k8s()
        if self._core_v1 is None:
            self._core_v1 = CoreV1Api(self._get_api_client())
        return self._core_v1

    @property
    def batch_v1(self) -> BatchV1Api:
        """BatchV1Api client, created on first use."""
        _load_k8s()
        if self._batch_v1 is None:
            self._batch_v1 = BatchV1Api(self._get_api_client())
        return self._batch_v1

    async def aclose(self) -> None:
        """Close the API client (application shutdown)."""
        if self._api_client is not None:
            await self._api_client.close()
        self._api_client = self._core_v1 = self._batch_v1 = None

    async def create_notebook_pod(
        self,
        name: str,
        experiment_id: str,
        prefix: str,
        token: str,
        notebook_resources: dict | None = None,
        gpu: bool = False,
        tier: NotebookTier | None = None,
    ) -> str:
        """
        Create a JupyterLab notebook pod for experiment setup.

        GROMACS and AmberTools binaries are bundled in the notebook image, so no sidecar is needed.

        Returns:
            The UID of the pod, for use as an owner reference on its service.
        """
        core_v1 = self.core_v1
        try:
            existing = await core_v1.read_namespaced_pod(name=name, namespace=NAMESPACE)
            logger.warning(f"Pod {name} already exists in namespace {NAMESPACE}. Skipping creation.")
            return str(existing.metadata.uid)
        except ApiException as e:
            if e.status != HTTPStatus.NOT_FOUND:
                raise

        volume_name = "shared-data"

        # Copy notebook resources to avoid mutating the original when adding GPU
        effective_nb = {k: dict(v) for k, v in (notebook_resources or {}).items()}
        if gpu and GPU_TYPE:
            effective_nb.setdefault("requests", {})[GPU_TYPE] = "1"
            effective_nb.setdefault("limits", {})[GPU_TYPE] = "1"

        jupyter_command = [
            "start.sh",
            "run-notebook.sh",
            f"--ServerApp.base_url={prefix}",
            f"--ServerApp.root_dir=/mddash/{experiment_id}",
            f"--ServerApp.token={token}",
            f"--NotebookApp.token={token}",
            f"--MappingKernelManager.cull_idle_timeout={NOTEBOOK_IDLE_TIMEOUT}",
            "--MappingKernelManager.cull_interval=120",
            "--MappingKernelManager.cull_connected=True",
            f"--ServerApp.shutdown_no_activity_timeout={NOTEBOOK_IDLE_TIMEOUT}",
        ]
        jupyter_env = [
            {"name": "WORKDIR", "value": f"/mddash/{experiment_id}"},
            {"name": "JUPYTER_DOCKER_STACKS_QUIET", "value": "1"},
            {
                "name": "JUPYTER_PATH",
                "value": f"/mddash/{experiment_id}/.binder-env/share/jupyter:/opt/conda/share/jupyter",
            },
            {"name": "MY_POD_NAME", "valueFrom": {"fieldRef": {"fieldPath": "metadata.name"}}},
        ]
        jupyter_container = get_container(
            "jupyter",
            NOTEBOOK_IMAGE,
            experiment_id,
            volume_name,
            jupyter_command,
            env=jupyter_env,
            resources=effective_nb,
        )

        labels = {"app": name, "type": "notebook"}
        if tier is not None:
            labels["tier"] = str(tier)
        labels["gpu"] = "true" if gpu and GPU_TYPE else "false"

        pod_manifest = {
            "apiVersion": "v1",
            "kind": "Pod",
            "metadata": {"name": name, "namespace": NAMESPACE, "labels": labels},
            "spec": {
                "securityContext": {
                    "fsGroup": 1000,
                    "fsGroupChangePolicy": "OnRootMismatch",
                    "supplementalGroups": [1000],
                },
                "containers": [jupyter_container],
                "volumes": [{"name": volume_name, "persistentVolumeClaim": {"claimName": PVC_NAME}}],
            },
        }

        # The client accepts plain manifest dicts; its stubs only declare model objects.
        created = await core_v1.create_namespaced_pod(namespace=NAMESPACE, body=cast("Any", pod_manifest))
        return str(created.metadata.uid)

    async def create_job(
        self,
        name: str,
        image: str,
        experiment_id: str,
        command: str,
        resources: dict | None = None,
    ) -> None:
        """
        Create a Job running `sh -c command` in /mddash/{experiment_id} (no retries, shared PVC).

        Args:
            name: The name of the job to create.
            image: The container image to use for the job.
            experiment_id: The ID of the experiment, used to set the working directory.
            command: The shell command to run.
            resources: Optional resource requests/limits dict.
        """
        if await self.ping_resource("job", name):
            logger.warning(f"Job {name} already exists in namespace {NAMESPACE}. Skipping creation.")
            return

        volume_name = "shared-data"
        job_container = get_container(
            name, image, experiment_id, volume_name, ["sh", "-c", command], resources=resources
        )
        job_manifest = {
            "apiVersion": "batch/v1",
            "kind": "Job",
            "metadata": {"name": name, "namespace": NAMESPACE, "labels": {"app": name}},
            "spec": {
                "backoffLimit": 0,
                "template": {
                    "metadata": {"labels": {"job": name}},
                    "spec": {
                        "restartPolicy": "Never",
                        "securityContext": {"fsGroup": 1000, "fsGroupChangePolicy": "OnRootMismatch"},
                        "containers": [job_container],
                        "volumes": [{"name": volume_name, "persistentVolumeClaim": {"claimName": PVC_NAME}}],
                    },
                },
            },
        }
        await self.batch_v1.create_namespaced_job(namespace=NAMESPACE, body=cast("Any", job_manifest))

    async def ping_resource(self, resource_type: str, name: str) -> bool:
        """
        Whether a resource exists in the namespace (False on any API error).

        Raises:
            ValueError: If resource_type is not a supported type.
        """
        try:
            match resource_type:
                case "svc":
                    await self.core_v1.read_namespaced_service(name=name, namespace=NAMESPACE)
                case "pod":
                    await self.core_v1.read_namespaced_pod(name=name, namespace=NAMESPACE)
                case "configmap":
                    await self.core_v1.read_namespaced_config_map(name=name, namespace=NAMESPACE)
                case "secret":
                    await self.core_v1.read_namespaced_secret(name=name, namespace=NAMESPACE)
                case "pvc":
                    await self.core_v1.read_namespaced_persistent_volume_claim(name=name, namespace=NAMESPACE)
                case "job":
                    await self.batch_v1.read_namespaced_job(name=name, namespace=NAMESPACE)
                case _:
                    raise ValueError(f"Unsupported resource type: {resource_type}")
            return True
        except ApiException:
            return False

    async def delete_pod(self, name: str) -> None:
        """Delete a pod if it exists."""
        if not await self.ping_resource("pod", name):
            return
        await self.core_v1.delete_namespaced_pod(name=name, namespace=NAMESPACE)

    async def delete_job(self, name: str) -> None:
        """Delete a job (background propagation) if it exists."""
        if not await self.ping_resource("job", name):
            return
        await self.batch_v1.delete_namespaced_job(
            name=name,
            namespace=NAMESPACE,
            body=V1DeleteOptions(propagation_policy="Background", grace_period_seconds=5),
        )

    async def delete_service(self, name: str) -> None:
        """Delete a service if it exists."""
        if not await self.ping_resource("svc", name):
            return
        await self.core_v1.delete_namespaced_service(name=name, namespace=NAMESPACE)

    async def create_service(self, name: str, target_name: str, target_uid: str) -> None:
        """
        Expose a pod (TCP 80 -> 8888), owned by the pod so K8s GC deletes both together.

        A lingering service owned by a deleted pod awaits GC, so existence alone must not skip creation.

        Args:
            name: The name of the service to create.
            target_name: The app label value of pods to target; must be the owning pod's name.
            target_uid: The UID of the owning pod.
        """
        core_v1 = self.core_v1
        try:
            existing = await core_v1.read_namespaced_service(name=name, namespace=NAMESPACE)
            owner_references = (existing.metadata.owner_references if existing.metadata else None) or []
            if owner_references and owner_references[0].uid == target_uid:
                logger.warning(f"Service {name} already exists in namespace {NAMESPACE}. Skipping creation.")
                return
            try:
                await core_v1.delete_namespaced_service(name=name, namespace=NAMESPACE)
            except ApiException as e:
                if e.status != HTTPStatus.NOT_FOUND:
                    raise
        except ApiException as e:
            if e.status != HTTPStatus.NOT_FOUND:
                raise

        service = V1Service(
            metadata=V1ObjectMeta(
                name=name,
                namespace=NAMESPACE,
                owner_references=[V1OwnerReference(api_version="v1", kind="Pod", name=target_name, uid=target_uid)],
            ),
            spec=V1ServiceSpec(
                selector={"app": target_name}, ports=[V1ServicePort(protocol="TCP", port=80, target_port=8888)]
            ),
        )
        await core_v1.create_namespaced_service(namespace=NAMESPACE, body=service)

    async def _get_active_pod_usage(self) -> dict[str, dict[str, int]]:
        """Total requests/limits of all active pods: {"requests": {"cpu", "memory"}, "limits": {...}}."""
        pods = await self.core_v1.list_namespaced_pod(namespace=NAMESPACE)
        totals: dict[str, dict[str, int]] = {"requests": {"cpu": 0, "memory": 0}, "limits": {"cpu": 0, "memory": 0}}

        for pod in pods.items or []:
            if not pod.spec or not pod.spec.containers:
                continue
            # Skip pods whose resources are already released
            if pod.status and pod.status.phase in {"Succeeded", "Failed"}:
                continue
            if pod.metadata and pod.metadata.deletion_timestamp:
                continue
            for resource_type in ("requests", "limits"):
                usage = _sum_container_resources(pod.spec.containers, resource_type)
                totals[resource_type]["cpu"] += usage["cpu"]
                totals[resource_type]["memory"] += usage["memory"]

        return totals

    async def count_notebook_pods(self) -> int:
        """Count Running/Pending notebook pods (excludes terminating)."""
        pods = await self.core_v1.list_namespaced_pod(namespace=NAMESPACE, label_selector="type=notebook")
        return sum(
            1
            for p in pods.items
            if (
                p.status
                and p.status.phase in {"Running", "Pending"}
                and p.metadata
                and not p.metadata.deletion_timestamp
            )
        )

    async def check_quota_headroom(
        self, cpu_request: int, memory_request: int, cpu_limit: int = 0, memory_limit: int = 0
    ) -> str | None:
        """
        Return an error message if spawning would exceed the namespace quota, else None.

        Best effort before pod/job creation; the K8s 403 stays the authoritative gate.

        Args:
            cpu_request: Additional CPU requests needed in millicores.
            memory_request: Additional memory requests needed in bytes.
            cpu_limit: Additional CPU limits needed in millicores.
            memory_limit: Additional memory limits needed in bytes.
        """
        usage = await self._get_active_pod_usage()

        quota_cpu = parse_cpu(CPU_REQUEST_QUOTA)
        quota_memory = parse_memory(MEMORY_REQUEST_QUOTA)
        if quota_cpu and usage["requests"]["cpu"] + cpu_request > quota_cpu:
            return (
                f"CPU quota would be exceeded: {usage['requests']['cpu']}m used + {cpu_request}m "
                f"requested > {quota_cpu}m namespace requests quota."
            )
        if quota_memory and usage["requests"]["memory"] + memory_request > quota_memory:
            used = usage["requests"]["memory"] / 1024**3
            req = memory_request / 1024**3
            quota = quota_memory / 1024**3
            return (
                f"Memory quota would be exceeded: {used:.1f}Gi used + {req:.1f}Gi "
                f"requested > {quota:.1f}Gi namespace requests quota."
            )

        quota_cpu_limit = parse_cpu(CPU_LIMIT_QUOTA)
        quota_memory_limit = parse_memory(MEMORY_LIMIT_QUOTA)
        if quota_cpu_limit and usage["limits"]["cpu"] + cpu_limit > quota_cpu_limit:
            return (
                f"CPU limits quota would be exceeded: {usage['limits']['cpu']}m used + {cpu_limit}m "
                f"requested > {quota_cpu_limit}m namespace limits quota."
            )
        if quota_memory_limit and usage["limits"]["memory"] + memory_limit > quota_memory_limit:
            used = usage["limits"]["memory"] / 1024**3
            req = memory_limit / 1024**3
            quota = quota_memory_limit / 1024**3
            return (
                f"Memory limits quota would be exceeded: {used:.1f}Gi used + {req:.1f}Gi "
                f"requested > {quota:.1f}Gi namespace limits quota."
            )

        return None

    async def get_pod_info(self, name: str) -> tuple[PodStatus, datetime | None]:
        """Pod (status, start_time) from one API read; start_time is None while the pod is absent."""
        try:
            pod = await self.core_v1.read_namespaced_pod(name=name, namespace=NAMESPACE)
        except ApiException as e:
            return (PodStatus.DOWN if e.status == HTTPStatus.NOT_FOUND else PodStatus.ERROR), None

        if not pod.metadata or not pod.status:
            return PodStatus.UNKNOWN, None

        start_time = pod.status.start_time
        if pod.metadata.deletion_timestamp:
            return PodStatus.TERMINATING, start_time

        match pod.status.phase:
            case "Running":
                if pod.status.container_statuses:
                    all_ready = all(container.ready for container in pod.status.container_statuses)
                    return (PodStatus.RUNNING if all_ready else PodStatus.PENDING), start_time
                return PodStatus.RUNNING, start_time
            case "Succeeded":
                return PodStatus.TERMINATED, start_time
            case "Failed":
                return PodStatus.ERROR, start_time
            case "Pending":
                return PodStatus.PENDING, start_time
        return PodStatus.UNKNOWN, start_time

    async def get_job_status(self, name: str) -> JobStatus:
        """Read the status of a Job (RUNNING, PENDING, FINISHED, ERROR, or UNKNOWN when absent)."""
        try:
            job = await self.batch_v1.read_namespaced_job(name=name, namespace=NAMESPACE)
        except ApiException as e:
            return JobStatus.UNKNOWN if e.status == HTTPStatus.NOT_FOUND else JobStatus.ERROR

        if not job.status:
            return JobStatus.UNKNOWN

        for condition in job.status.conditions or []:
            if condition.type == "Complete" and condition.status == "True":
                return JobStatus.FINISHED
            if condition.type == "Failed" and condition.status == "True":
                return JobStatus.ERROR

        if job.status.succeeded and job.status.succeeded > 0:
            return JobStatus.FINISHED
        if job.status.failed and job.status.failed > 0:
            return JobStatus.ERROR
        if job.status.active and job.status.active > 0:
            return JobStatus.RUNNING
        return JobStatus.PENDING

    async def get_job_logs(self, name: str, tail_lines: int = 200) -> str:
        """Read the logs of a Job's pod, or an empty string when the pod is gone or the API errors."""
        try:
            core_v1 = self.core_v1
            pods = await core_v1.list_namespaced_pod(namespace=NAMESPACE, label_selector=f"job={name}")
            if not pods.items:
                return ""
            pod_name = pods.items[0].metadata.name
            # Raw bytes decoded with replacement: large logs may be truncated mid-character.
            # Unpreloaded content is the raw aiohttp response (the stubs declare the decoded str).
            response: Any = await core_v1.read_namespaced_pod_log(
                name=pod_name, namespace=NAMESPACE, tail_lines=tail_lines, _preload_content=False
            )
            return (await response.read()).decode("utf-8", errors="replace")
        except ApiException:
            return ""

    async def read_job(self, name: str) -> object | None:
        """Return the Job, or None if not found (404); re-raises other API errors."""
        try:
            return await self.batch_v1.read_namespaced_job(name=name, namespace=NAMESPACE)
        except ApiException as e:
            if e.status == HTTPStatus.NOT_FOUND:
                return None
            raise

    async def delete_job_foreground(self, name: str) -> None:
        """Delete a Job with foreground propagation (pods first)."""
        if not await self.ping_resource("job", name):
            return
        try:
            await self.batch_v1.delete_namespaced_job(
                name=name,
                namespace=NAMESPACE,
                body=V1DeleteOptions(propagation_policy="Foreground", grace_period_seconds=0),
            )
        except ApiException as e:
            if e.status != HTTPStatus.NOT_FOUND:
                raise

    async def list_pods_by_label(self, label_selector: str) -> list:
        """Pods matching a label selector."""
        result = await self.core_v1.list_namespaced_pod(namespace=NAMESPACE, label_selector=label_selector)
        return result.items if result and result.items else []

    async def wait_for_pod_admission(self, label_selector: str, max_wait: int = 30) -> bool:
        """Poll until a pod reaches Running, Succeeded, or Failed (admitted, not Pending)."""
        deadline = time.monotonic() + max_wait
        while time.monotonic() < deadline:
            for pod in await self.list_pods_by_label(label_selector):
                phase = getattr(getattr(pod, "status", None), "phase", None)
                if phase in {"Running", "Succeeded", "Failed"}:
                    return True
            await asyncio.sleep(1)
        return False

    async def wait_for_resource_absence(self, resource_type: str, name: str, max_wait: int = 30) -> bool:
        """Poll until the resource no longer exists."""
        deadline = time.monotonic() + max_wait
        while time.monotonic() < deadline:
            if not await self.ping_resource(resource_type, name):
                return True
            await asyncio.sleep(1)
        return False

    async def create_job_raw(self, manifest: dict) -> None:
        """Create a Job from a complete manifest dict."""
        await self.batch_v1.create_namespaced_job(namespace=NAMESPACE, body=cast("Any", manifest))
