import logging
import threading
import time
from http import HTTPStatus
from typing import Callable, cast

from config import GMX_IMAGE, IMAGE_PULL_POLICY, NAMESPACE, NOTEBOOK_IMAGE, PVC_NAME
from enums import JobStatus, PodStatus
from kubernetes import config
from kubernetes.client import (
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
from kubernetes.client.rest import ApiException

logger = logging.getLogger(__name__)


config.load_incluster_config()
core_v1 = CoreV1Api()
batch_v1 = BatchV1Api()


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


def create_notebook_pod(name: str, experiment_id: str, prefix: str, token: str) -> None:
    """
    Create a JupyterLab notebook pod with GROMACS tools for experiment setup.

    Creates a pod with three containers: a Jupyter notebook server, a GROMACS container,
    and an init container that sets up the working directory. The pod uses a PVC for
    persistent storage.

    Args:
        name: The name of the pod to create.
        experiment_id: The ID of the experiment (used for directory path).
        prefix: The base URL prefix for the notebook server.
        token: Authentication token for accessing the notebook.

    """
    if ping_resource("pod", name):
        logger.warning(f"Pod {name} already exists in namespace {NAMESPACE}. Skipping creation.")
        return

    volume_name = "shared-data"
    gmx_container = get_container(
        "gmx",
        GMX_IMAGE,
        experiment_id,
        volume_name,
        ["sleep", "infinity"],
        resources={"requests": {"cpu": "100m", "memory": "256Mi"}, "limits": {"cpu": "2000m", "memory": "2Gi"}},
    )

    jupyter_command = [
        "start.sh",
        "start-with-binder.sh",
        f"--ServerApp.base_url={prefix}",
        f"--ServerApp.root_dir=/mddash/{experiment_id}",
        f"--ServerApp.token={token}",
        f"--NotebookApp.token={token}",
    ]
    jupyter_env = [
        {"name": "WORKDIR", "value": f"/mddash/{experiment_id}"},
        {"name": "JUPYTER_DOCKER_STACKS_QUIET", "value": "1"},
        {
            "name": "JUPYTER_PATH",
            "value": f"/mddash/{experiment_id}/.binder-env/share/jupyter:/opt/conda/share/jupyter",
        },
    ]
    jupyter_resources = {"requests": {"cpu": "200m", "memory": "512Mi"}, "limits": {"cpu": "2000m", "memory": "4Gi"}}
    jupyter_container = get_container(
        "jupyter",
        NOTEBOOK_IMAGE,
        experiment_id,
        volume_name,
        jupyter_command,
        env=jupyter_env,
        resources=jupyter_resources,
    )

    pod_manifest = {
        "apiVersion": "v1",
        "kind": "Pod",
        "metadata": {"name": name, "namespace": NAMESPACE, "labels": {"app": name}},
        "spec": {
            "securityContext": {"fsGroup": 1000, "fsGroupChangePolicy": "OnRootMismatch", "supplementalGroups": [1000]},
            "containers": [jupyter_container, gmx_container],
            "volumes": [{"name": volume_name, "persistentVolumeClaim": {"claimName": PVC_NAME}}],
        },
    }

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

    core_v1.delete_namespaced_pod(name=name, namespace=NAMESPACE)


def delete_job(name: str) -> None:
    """
    Delete a job from the namespace with background propagation.

    Args:
        name: The name of the job to delete.

    """
    if not ping_resource("job", name):
        return

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


def get_pod_resource_requests() -> dict:
    """
    Calculate total resource requests for all pods in the namespace.

    Iterates through all pods and sums up CPU and memory resource requests.
    Handles multiple unit formats (m for millicores, Mi/Gi for memory).

    Returns:
        dict: Dictionary with 'cpu' (millicores) and 'memory' (bytes).
    """
    pods = cast("V1PodList", core_v1.list_namespaced_pod(namespace=NAMESPACE))

    requests_total = {"cpu": 0, "memory": 0}

    if not pods.items:
        return requests_total

    for pod in pods.items:
        if not pod.spec or not pod.spec.containers:
            continue
        requests = _sum_container_resources(pod.spec.containers, "requests")
        requests_total["cpu"] += requests["cpu"]
        requests_total["memory"] += requests["memory"]

    return requests_total


def get_pod_status(name: str) -> PodStatus:
    """
    Get the current status of a pod.

    Args:
        name: The name of the pod.

    Returns:
        PodStatus: The current status (RUNNING, PENDING, TERMINATED, ERROR, DOWN, TERMINATING, or UNKNOWN).
    """
    try:
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
