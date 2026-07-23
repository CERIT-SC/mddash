from __future__ import annotations

import logging
import threading
import time
from http import HTTPStatus
from typing import TYPE_CHECKING, Callable, cast

if TYPE_CHECKING:
    from enums import NotebookTier

    # Available at runtime via _load_k8s() populating module globals.
    from kubernetes import config  # ruff:ignore[runtime-import-in-type-checking-block]
    from kubernetes.client import (  # ruff:ignore[runtime-import-in-type-checking-block]
        BatchV1Api,
        CoreV1Api,
        V1DeleteOptions,
        V1Job,
        V1ObjectMeta,
        V1Pod,
        V1PodList,
        V1Service,
        V1ServicePort,
        V1ServiceSpec,
    )
    from kubernetes.client.rest import ApiException  # ruff:ignore[runtime-import-in-type-checking-block]

from config import (
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
from enums import JobStatus, PodStatus

logger = logging.getLogger(__name__)

_k8s_lock = threading.Lock()
_k8s_loaded = False
_k8s_config_loaded = False
_core_v1: CoreV1Api | None = None
_batch_v1: BatchV1Api | None = None


def _load_k8s() -> None:
    """Import kubernetes symbols into module globals on first k8s use."""
    global _k8s_loaded  # ruff:ignore[global-statement]
    if _k8s_loaded:
        return
    import kubernetes.config  # ruff:ignore[import-outside-top-level]
    from kubernetes.client import (  # ruff:ignore[import-outside-top-level]
        BatchV1Api,
        CoreV1Api,
        V1DeleteOptions,
        V1ObjectMeta,
        V1Service,
        V1ServicePort,
        V1ServiceSpec,
    )
    from kubernetes.client.rest import ApiException  # ruff:ignore[import-outside-top-level]

    g = globals()
    g["config"] = kubernetes.config
    g.update(
        BatchV1Api=BatchV1Api,
        CoreV1Api=CoreV1Api,
        V1DeleteOptions=V1DeleteOptions,
        V1ObjectMeta=V1ObjectMeta,
        V1Service=V1Service,
        V1ServicePort=V1ServicePort,
        V1ServiceSpec=V1ServiceSpec,
        ApiException=ApiException,
    )
    _k8s_loaded = True


def _ensure_k8s_config() -> None:
    global _k8s_config_loaded  # ruff:ignore[global-statement]
    if not _k8s_config_loaded:
        _load_k8s()
        config.load_incluster_config()
        _k8s_config_loaded = True


def get_core_v1() -> CoreV1Api:
    """Return a cached CoreV1Api client, loading in-cluster config on first use."""  # ruff:ignore[docstring-missing-returns]
    global _core_v1  # ruff:ignore[global-statement]
    if _core_v1 is None:
        with _k8s_lock:
            if _core_v1 is None:
                _ensure_k8s_config()
                _core_v1 = CoreV1Api()
    return _core_v1


def get_batch_v1() -> BatchV1Api:
    """Return a cached BatchV1Api client, loading in-cluster config on first use."""  # ruff:ignore[docstring-missing-returns]
    global _batch_v1  # ruff:ignore[global-statement]
    if _batch_v1 is None:
        with _k8s_lock:
            if _batch_v1 is None:
                _ensure_k8s_config()
                _batch_v1 = BatchV1Api()
    return _batch_v1


def reset_k8s_clients_for_tests() -> None:
    """Reset cached Kubernetes clients for isolated unit tests."""
    global _batch_v1, _core_v1, _k8s_config_loaded, _k8s_loaded  # ruff:ignore[global-statement]
    _core_v1 = None
    _batch_v1 = None
    _k8s_config_loaded = False
    _k8s_loaded = False


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
    Create a container specification with security context and volume mounts.

    Generates a Kubernetes container spec with security best practices (non-root user,
    dropped capabilities, seccomp profile) and mounts the shared volume at /mddash.

    Args:
        name: The name of the container.
        image: The container image to use.
        experiment_id: The ID of the experiment, used to set the working directory.
        volume_name: The name of the volume to mount at /mddash.
        command: The command to run in the container.
        env: Optional list of environment variable dictionaries with 'name' and 'value' keys.
        set_working_dir: Whether to set the working directory to /mddash/{experiment_id}.
        resources: Optional resource requests/limits dict. Defaults to 100m CPU and 128Mi memory.

    Returns:
        dict: Container specification dictionary for Kubernetes pod/job manifest.
    """
    container = {
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


def create_notebook_pod(
    name: str,
    experiment_id: str,
    prefix: str,
    token: str,
    notebook_resources: dict | None = None,
    gpu: bool = False,
    tier: "NotebookTier | None" = None,
) -> None:
    """
    Create a JupyterLab notebook pod for experiment setup.

    Creates a pod with a single Jupyter container. GROMACS and AmberTools
    binaries are bundled in the notebook image — no sidecar needed.

    Args:
        name: The name of the pod to create.
        experiment_id: The ID of the experiment (used for directory path).
        prefix: The base URL prefix for the notebook server.
        token: Authentication token for accessing the notebook.
        notebook_resources: Resource requests/limits for the Jupyter container.
        gpu: Whether to attach a GPU to the jupyter container.
        tier: The resource tier for pod labeling.

    """
    if ping_resource("pod", name):
        logger.warning(f"Pod {name} already exists in namespace {NAMESPACE}. Skipping creation.")
        return

    volume_name = "shared-data"

    # Deep copy notebook resources to avoid mutating the original when adding GPU
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
            "securityContext": {"fsGroup": 1000, "fsGroupChangePolicy": "OnRootMismatch", "supplementalGroups": [1000]},
            "containers": [jupyter_container],
            "volumes": [{"name": volume_name, "persistentVolumeClaim": {"claimName": PVC_NAME}}],
        },
    }

    core_v1 = get_core_v1()
    core_v1.create_namespaced_pod(namespace=NAMESPACE, body=pod_manifest)


def create_job(
    name: str,
    image: str,
    experiment_id: str,
    command: str,
    resources: dict | None = None,
) -> None:
    """
    Create a Kubernetes job that runs a command in the experiment directory.

    Creates a batch job with a single container that executes the specified command
    in /mddash/{experiment_id}. The job uses the shared PVC for persistent storage
    and has backoffLimit set to 0 (no retries on failure).

    Args:
        name: The name of the job to create.
        image: The container image to use for the job.
        experiment_id: The ID of the experiment, used to set the working directory.
        command: The shell command to run (will be wrapped in sh -c).
        resources: Optional resource requests/limits dict. Defaults to 50m CPU and 64Mi memory.

    """
    if ping_resource("job", name):
        logger.warning(f"Job {name} already exists in namespace {NAMESPACE}. Skipping creation.")
        return

    volume_name = "shared-data"

    job_container = get_container(name, image, experiment_id, volume_name, ["sh", "-c", command], resources=resources)

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

    batch_v1 = get_batch_v1()
    batch_v1.create_namespaced_job(namespace=NAMESPACE, body=job_manifest)


def ping_resource(resource_type: str, name: str) -> bool:
    """
    Check if a Kubernetes resource exists in the namespace.

    Args:
        resource_type: The type of resource ('svc', 'pod', 'configmap', 'secret', 'pvc', or 'job').
        name: The name of the resource to check.

    Returns:
        bool: True if the resource exists, False if not found or on API error.

    Raises:
        ValueError: If resource_type is not a supported type.
    """
    try:
        core_v1 = get_core_v1()
        batch_v1 = get_batch_v1()
        match resource_type:
            case "svc":
                core_v1.read_namespaced_service(name=name, namespace=NAMESPACE)
            case "pod":
                core_v1.read_namespaced_pod(name=name, namespace=NAMESPACE)
            case "configmap":
                core_v1.read_namespaced_config_map(name=name, namespace=NAMESPACE)
            case "secret":
                core_v1.read_namespaced_secret(name=name, namespace=NAMESPACE)
            case "pvc":
                core_v1.read_namespaced_persistent_volume_claim(name=name, namespace=NAMESPACE)
            case "job":
                batch_v1.read_namespaced_job(name=name, namespace=NAMESPACE)
            case _:
                raise ValueError(f"Unsupported resource type: {resource_type}")
        return True
    except ApiException:
        return False


def delete_pod(name: str) -> None:
    """
    Delete a pod from the namespace.

    Args:
        name: The name of the pod to delete.

    """
    if not ping_resource("pod", name):
        return

    core_v1 = get_core_v1()
    core_v1.delete_namespaced_pod(name=name, namespace=NAMESPACE)


def delete_job(name: str) -> None:
    """
    Delete a job from the namespace with background propagation.

    Args:
        name: The name of the job to delete.

    """
    if not ping_resource("job", name):
        return

    batch_v1 = get_batch_v1()
    batch_v1.delete_namespaced_job(
        name=name,
        namespace=NAMESPACE,
        body=V1DeleteOptions(
            propagation_policy="Background",
            grace_period_seconds=5,
        ),
    )


def delete_service(name: str) -> None:
    """
    Delete a service from the namespace.

    Args:
        name: The name of the service to delete.

    """
    if not ping_resource("svc", name):
        return

    core_v1 = get_core_v1()
    core_v1.delete_namespaced_service(name=name, namespace=NAMESPACE)


def create_service(name: str, target_name: str) -> None:
    """
    Create a Kubernetes service to expose a pod.

    Creates a service that routes TCP traffic on port 80 to port 8888 of pods
    matching the target app label.

    Args:
        name: The name of the service to create.
        target_name: The app label value of pods to target.

    """
    if ping_resource("svc", name):
        logger.warning(f"Service {name} already exists in namespace {NAMESPACE}. Skipping creation.")
        return

    service = V1Service(
        metadata=V1ObjectMeta(name=name, namespace=NAMESPACE),
        spec=V1ServiceSpec(
            selector={"app": target_name}, ports=[V1ServicePort(protocol="TCP", port=80, target_port=8888)]
        ),
    )

    core_v1 = get_core_v1()
    core_v1.create_namespaced_service(namespace=NAMESPACE, body=service)


def parse_cpu(cpu_str: str | None) -> int:
    """
    Parse CPU value from Kubernetes format to millicores.

    Args:
        cpu_str: CPU value (e.g., '100m', '1', '1.5').

    Returns:
        int: CPU value in millicores.
    """
    if not cpu_str:
        return 0

    cpu_str = str(cpu_str)
    if cpu_str.endswith("m"):
        return int(cpu_str[:-1])
    return int(float(cpu_str) * 1000)


def parse_memory(mem_str: str | None) -> int:
    """
    Parse memory value from Kubernetes format to bytes.

    Args:
        mem_str: Memory value (e.g., '128Mi', '1Gi', '1G').

    Returns:
        int: Memory value in bytes.
    """
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

    # Try to parse as plain number (bytes)
    try:
        return int(float(mem_str))
    except (ValueError, TypeError):
        logger.warning(f"Unable to parse memory value: {mem_str}")
        return 0


def _sum_container_resources(containers: list, resource_type: str) -> dict:
    """
    Sum CPU and memory resources for a list of containers.

    Args:
        containers: List of Kubernetes container objects.
        resource_type: Either 'requests' or 'limits'.

    Returns:
        dict: Dictionary with 'cpu' (millicores) and 'memory' (bytes) totals.
    """
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


def _get_active_pod_usage() -> dict[str, dict[str, int]]:
    """
    Calculate total resource requests and limits for all active pods in the namespace.

    Returns:
        dict: {"requests": {"cpu": millicores, "memory": bytes}, "limits": {...}}
    """
    core_v1 = get_core_v1()
    pods = cast("V1PodList", core_v1.list_namespaced_pod(namespace=NAMESPACE))
    totals: dict[str, dict[str, int]] = {"requests": {"cpu": 0, "memory": 0}, "limits": {"cpu": 0, "memory": 0}}

    if not pods.items:
        return totals

    for pod in pods.items:
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


def get_pod_resource_requests() -> dict[str, int]:
    """
    Return total CPU and memory requests for all active pods in the namespace.

    Returns:
        dict: Dictionary with 'cpu' (millicores) and 'memory' (bytes) totals.
    """
    return _get_active_pod_usage()["requests"]


def count_notebook_pods() -> int:
    """
    Return count of Running/Pending notebook pods (excludes terminating).

    Returns:
        int: Number of active (non-terminating) notebook pods.
    """
    core_v1 = get_core_v1()
    pods = core_v1.list_namespaced_pod(namespace=NAMESPACE, label_selector="type=notebook")
    return sum(
        1
        for p in pods.items
        if (p.status and p.status.phase in {"Running", "Pending"} and p.metadata and not p.metadata.deletion_timestamp)
    )


def check_quota_headroom(
    cpu_request: int, memory_request: int, cpu_limit: int = 0, memory_limit: int = 0
) -> str | None:
    """
    Return an error message if spawning would exceed the namespace quota, else None.

    This is a best-effort check before pod/job creation. The existing K8s 403 handler
    remains the authoritative enforcement gate.

    Args:
        cpu_request: Additional CPU requests needed in millicores.
        memory_request: Additional memory requests needed in bytes.
        cpu_limit: Additional CPU limits needed in millicores.
        memory_limit: Additional memory limits needed in bytes.

    Returns:
        str | None: An error message if quota would be exceeded, else None.
    """
    usage = _get_active_pod_usage()

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


def get_pod_status(name: str) -> PodStatus:
    """
    Get the current status of a pod.

    Args:
        name: The name of the pod.

    Returns:
        PodStatus: The current status (RUNNING, PENDING, TERMINATED, ERROR, DOWN, TERMINATING, or UNKNOWN).
    """
    try:
        core_v1 = get_core_v1()
        pod = cast("V1Pod", core_v1.read_namespaced_pod(name=name, namespace=NAMESPACE))

        if not pod.metadata or not pod.status:
            return PodStatus.UNKNOWN

        if pod.metadata.deletion_timestamp:
            return PodStatus.TERMINATING

        phase = pod.status.phase

        if phase == "Running":
            # Check if all containers are ready
            if pod.status.container_statuses:
                all_ready = all(container.ready for container in pod.status.container_statuses)
                return PodStatus.RUNNING if all_ready else PodStatus.PENDING
            return PodStatus.RUNNING
        if phase == "Succeeded":
            return PodStatus.TERMINATED
        if phase == "Failed":
            return PodStatus.ERROR
        if phase == "Pending":
            return PodStatus.PENDING

        return PodStatus.UNKNOWN

    except ApiException as e:
        return PodStatus.DOWN if e.status == HTTPStatus.NOT_FOUND else PodStatus.ERROR


def get_job_status(name: str) -> JobStatus:
    """
    Get the current status of a job.

    Args:
        name: The name of the job.

    Returns:
        JobStatus: The current status (RUNNING, PENDING, TERMINATED, ERROR, or UNKNOWN).
    """
    try:
        batch_v1 = get_batch_v1()
        job = cast("V1Job", batch_v1.read_namespaced_job(name=name, namespace=NAMESPACE))

        if not job.status:
            return JobStatus.UNKNOWN

        if job.status.conditions:
            for condition in job.status.conditions:
                if condition.type == "Complete" and condition.status == "True":
                    return JobStatus.TERMINATED
                if condition.type == "Failed" and condition.status == "True":
                    return JobStatus.ERROR

        if job.status.succeeded and job.status.succeeded > 0:
            return JobStatus.TERMINATED
        if job.status.failed and job.status.failed > 0:
            return JobStatus.ERROR
        if job.status.active and job.status.active > 0:
            return JobStatus.RUNNING

        return JobStatus.PENDING

    except ApiException as e:
        if e.status == HTTPStatus.NOT_FOUND:
            return JobStatus.UNKNOWN
        return JobStatus.ERROR


def get_job_logs(name: str, tail_lines: int = 200) -> str:
    """
    Get logs from the pod belonging to a job.

    Returns:
        Log text as a string, or empty string if the pod is not found or an error occurs.
    """
    try:
        core_v1 = get_core_v1()
        pods = core_v1.list_namespaced_pod(namespace=NAMESPACE, label_selector=f"job={name}")
        if not pods.items:
            return ""
        pod_name = pods.items[0].metadata.name
        # _preload_content=False gives raw bytes so we can decode with error replacement,
        # avoiding UnicodeDecodeError when large log output is truncated mid-stream.
        response = core_v1.read_namespaced_pod_log(
            name=pod_name, namespace=NAMESPACE, tail_lines=tail_lines, _preload_content=False
        )
        return response.data.decode("utf-8", errors="replace")
    except ApiException:
        return ""


def wait_for_job(
    name: str, on_success: Callable[[], None], on_error: Callable[[Exception], None], timeout: int = 60
) -> None:
    """
    Wait for a Kubernetes job to complete asynchronously and execute callbacks.

    Spawns a daemon thread that polls the job status every 2 seconds until completion,
    failure, or timeout. Executes the appropriate callback based on the outcome.

    Args:
        name: Name of the job to wait for.
        on_success: Callback function to invoke when the job completes successfully.
        on_error: Callback function to invoke with the exception when the job fails or times out.
        timeout: Maximum time to wait in seconds (default: 60).
    """

    def wait_and_callback() -> None:
        try:
            start_time = time.time()
            while time.time() - start_time < timeout:
                status = get_job_status(name)
                if status == JobStatus.TERMINATED:
                    on_success()
                    return
                if status == JobStatus.ERROR:
                    raise RuntimeError(f"Job {name} failed")
                time.sleep(2)

            raise RuntimeError(f"Job {name} timed out after {timeout}s")
        except Exception as e:
            on_error(e)

    thread = threading.Thread(target=wait_and_callback, daemon=True)
    thread.start()


def read_job(name: str) -> object | None:
    """
    Return None if not found (404).

    Returns:
        The Job object, or None.

    Raises:
        ApiException: If the read fails for a reason other than 404.
    """
    try:
        batch_v1 = get_batch_v1()
        return batch_v1.read_namespaced_job(name=name, namespace=NAMESPACE)
    except ApiException as e:
        if e.status == HTTPStatus.NOT_FOUND:
            return None
        raise


def delete_job_foreground(name: str) -> None:
    """
    Foreground propagation blocks until pods are deleted.

    Raises:
        ApiException: If the delete fails for a reason other than 404.
    """
    if not ping_resource("job", name):
        return
    batch_v1 = get_batch_v1()
    try:
        batch_v1.delete_namespaced_job(
            name=name,
            namespace=NAMESPACE,
            body=V1DeleteOptions(
                propagation_policy="Foreground",
                grace_period_seconds=0,
            ),
        )
    except ApiException as e:
        if e.status != HTTPStatus.NOT_FOUND:
            raise


def list_pods_by_label(label_selector: str) -> list:
    """
    List pods matching a label selector.

    Returns:
        List of pod objects.
    """
    core_v1 = get_core_v1()
    result = core_v1.list_namespaced_pod(namespace=NAMESPACE, label_selector=label_selector)
    return result.items if result and result.items else []


def wait_for_pod_admission(label_selector: str, timeout: int = 30) -> bool:
    """
    Poll until a pod reaches Running, Succeeded, or Failed (i.e. admitted, not Pending).

    Returns:
        True if admitted, False if timed out.
    """
    deadline = time.time() + timeout
    while time.time() < deadline:
        pods = list_pods_by_label(label_selector)
        for pod in pods:
            phase = getattr(getattr(pod, "status", None), "phase", None)
            if phase in {"Running", "Succeeded", "Failed"}:
                return True
        time.sleep(1)
    return False


def wait_for_resource_absence(resource_type: str, name: str, timeout: int = 30) -> bool:
    """
    Poll until a resource is gone.

    Returns:
        True if gone, False if still exists after timeout.
    """
    deadline = time.time() + timeout
    while time.time() < deadline:
        if not ping_resource(resource_type, name):
            return True
        time.sleep(1)
    return False


def create_job_raw(manifest: dict) -> None:
    """Accept a complete manifest dict (unlike create_job which builds it from params)."""
    batch_v1 = get_batch_v1()
    batch_v1.create_namespaced_job(namespace=NAMESPACE, body=manifest)
