import logging
import threading
from typing import Callable
from kubernetes import client, config  # type: ignore
from kubernetes.client.rest import ApiException  # type: ignore

from enums import PodStatus, JobStatus
from config import GPU_TYPE, NOTEBOOK_IMAGE, GMX_IMAGE, NAMESPACE, PVC_NAME


logger = logging.getLogger(__name__)


config.load_incluster_config()
core_v1 = client.CoreV1Api()
batch_v1 = client.BatchV1Api()


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
    """Create a container specification with security context and volume mounts.

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
        'securityContext': {
            'runAsUser': 1000,
            'runAsGroup': 1000,
            'runAsNonRoot': True,
            'allowPrivilegeEscalation': False,
            'capabilities': {
                'drop': ['ALL']
            },
            'seccompProfile': {
                'type': 'RuntimeDefault'
            }
        },
        'name': name,
        'image': image,
        'imagePullPolicy': 'Always',  # TODO: maybe IfNotPresent?
        'resources': resources or {
            'requests': {'cpu': '100m', 'memory': '128Mi'},
            'limits': {'cpu': '200m', 'memory': '256Mi'}
        },
        'command': command,
        'volumeMounts': [
            {'mountPath': '/mddash', 'name': volume_name}
        ]
    }

    if set_working_dir:
        container['workingDir'] = f'/mddash/{experiment_id}'

    if env:
        container['env'] = env

    return container


def create_notebook_pod(name: str, experiment_id: str, prefix: str, token: str) -> None:
    """Create a JupyterLab notebook pod with GROMACS tools for experiment setup.

    Creates a pod with three containers: a Jupyter notebook server, a GROMACS container,
    and an init container that sets up the working directory. The pod uses a PVC for
    persistent storage.

    Args:
        name: The name of the pod to create.
        experiment_id: The ID of the experiment (used for directory path).
        prefix: The base URL prefix for the notebook server.
        token: Authentication token for accessing the notebook.
    Raises:
        ApiException: If an error occurs while creating the pod.
    """
    if ping_resource('pod', name):
        logger.warning(f"Pod {name} already exists in namespace {NAMESPACE}. Skipping creation.")
        return

    workdir_init_command = f"""
        if [ ! -d "/mddash/{experiment_id}" ]; then
            mkdir -p /mddash/{experiment_id}
        fi

        if [ ! -w "/mddash/{experiment_id}" ]; then
            echo "Notebook directory /mddash/{experiment_id} is not writable" >&2
            exit 1
        fi

        if ls /home/jovyan/*.ipynb 1> /dev/null 2>&1; then
            echo "Preparing notebook templates in /mddash/{experiment_id}"
            for n in /home/jovyan/*.ipynb; do 
                b=$(basename "$n")
                if [ -f "/mddash/{experiment_id}/$b" ]; then
                    echo "Template $b exists, writing $b.new"
                    cp "$n" "/mddash/{experiment_id}/$b.new"
                else
                    echo "Copying template $b"
                    cp "$n" "/mddash/{experiment_id}/$b"
                fi
            done
            echo "Notebook templates ready in /mddash/{experiment_id}"
        else
            echo "No notebook templates found, skipping copy"
        fi
    """

    volume_name = 'shared-data'
    workdir_init_container = get_container(
        'workdir-init',
        NOTEBOOK_IMAGE,
        experiment_id,
        volume_name,
        ['sh', '-c', workdir_init_command],
        set_working_dir=False
    )
    gmx_container = get_container('gmx', GMX_IMAGE, experiment_id, volume_name, ['sleep', 'infinity'])

    jupyter_command = [
        'start-notebook.sh',
        f'--NotebookApp.base_url={prefix}',
        f'--NotebookApp.notebook_dir=/mddash/{experiment_id}',
        f'--NotebookApp.token="{token}"'
    ]
    jupyter_env = [{'name': 'WORKDIR', 'value': f'/mddash/{experiment_id}'}]
    jupyter_resources = {
        'requests': {'cpu': '100m', 'memory': '512Mi'},
        'limits': {'cpu': '2000m', 'memory': '8Gi'}
    }
    jupyter_container = get_container(
        'jupyter',
        NOTEBOOK_IMAGE,
        experiment_id,
        volume_name,
        jupyter_command,
        env=jupyter_env,
        resources=jupyter_resources
    )

    pod_manifest = {
        'apiVersion': 'v1',
        'kind': 'Pod',
        'metadata': {
            'name': name,
            'namespace': NAMESPACE,
            'labels': {
                'app': name
            }
        },
        'spec': {
            'securityContext': {
                'fsGroup': 1000,
                'fsGroupChangePolicy': 'Always',
                'supplementalGroups': [1000]
            },
            'initContainers': [
                workdir_init_container
            ],
            'containers': [
                jupyter_container,
                gmx_container
            ],
            'volumes': [
                {
                    'name': volume_name,
                    'persistentVolumeClaim': {
                        'claimName': PVC_NAME
                    }
                }
            ]
        }
    }

    core_v1.create_namespaced_pod(namespace=NAMESPACE, body=pod_manifest)


def create_job(name: str, image: str, experiment_id: str, command: str) -> None:
    """Create a Kubernetes job that runs a command in the experiment directory.

    Creates a batch job with a single container that executes the specified command
    in /mddash/{experiment_id}. The job uses the shared PVC for persistent storage
    and has backoffLimit set to 0 (no retries on failure).

    Args:
        name: The name of the job to create.
        image: The container image to use for the job.
        experiment_id: The ID of the experiment, used to set the working directory.
        command: The shell command to run (will be wrapped in sh -c).
    Raises:
        ApiException: If an error occurs while creating the job.
    """

    if ping_resource('job', name):
        logger.warning(f"Job {name} already exists in namespace {NAMESPACE}. Skipping creation.")
        return

    volume_name = 'shared-data'

    job_container = get_container(name, image, experiment_id, volume_name, ['sh', '-c', command])

    job_manifest = {
        'apiVersion': 'batch/v1',
        'kind': 'Job',
        'metadata': {
            'name': name,
            'namespace': NAMESPACE,
            'labels': {
                'app': name
            }
        },
        'spec': {
            'backoffLimit': 0,
            'template': {
                'metadata': {
                    'labels': {
                        'job': name
                    }
                },
                'spec': {
                    'restartPolicy': 'Never',
                    'securityContext': {
                        'fsGroup': 1000
                    },
                    'containers': [
                        job_container
                    ],
                    'volumes': [
                        {
                            'name': volume_name,
                            'persistentVolumeClaim': {
                                'claimName': PVC_NAME
                            }
                        }
                    ]
                }
            }
        }
    }

    batch_v1.create_namespaced_job(namespace=NAMESPACE, body=job_manifest)


def ping_resource(resource_type: str, name: str) -> bool:
    """Check if a Kubernetes resource exists in the namespace.

    Args:
        resource_type: The type of resource ('svc', 'pod', 'configmap', 'secret', 'pvc', or 'job').
        name: The name of the resource to check.
    Returns:
        bool: True if the resource exists, False if not found or on API error.
    """

    try:
        match resource_type:
            case 'svc':
                core_v1.read_namespaced_service(name=name, namespace=NAMESPACE)
            case 'pod':
                core_v1.read_namespaced_pod(name=name, namespace=NAMESPACE)
            case 'configmap':
                core_v1.read_namespaced_config_map(name=name, namespace=NAMESPACE)
            case 'secret':
                core_v1.read_namespaced_secret(name=name, namespace=NAMESPACE)
            case 'pvc':
                core_v1.read_namespaced_persistent_volume_claim(
                    name=name, namespace=NAMESPACE)
            case 'job':
                batch_v1.read_namespaced_job(name=name, namespace=NAMESPACE)
            case _:
                raise ValueError(f"Unsupported resource type: {resource_type}")
        return True
    except ApiException as e:
        return False


def delete_pod(name: str) -> None:
    """Delete a pod from the namespace.

    Args:
        name: The name of the pod to delete.
    Raises:
        ApiException: If an error occurs while deleting the pod.
    """
    if not ping_resource('pod', name):
        return

    core_v1.delete_namespaced_pod(name=name, namespace=NAMESPACE)


def delete_job(name: str) -> None:
    """Delete a job from the namespace with background propagation.

    Args:
        name: The name of the job to delete.
    Raises:
        ApiException: If an error occurs while deleting the job.
    """
    if not ping_resource('job', name):
        return

    batch_v1.delete_namespaced_job(
        name=name,
        namespace=NAMESPACE,
        body=client.V1DeleteOptions(
            propagation_policy='Background',
            grace_period_seconds=5,
        )
    )


def delete_service(name: str) -> None:
    """Delete a service from the namespace.

    Args:
        name: The name of the service to delete.
    Raises:
        ApiException: If an error occurs while deleting the service.
    """
    if not ping_resource('svc', name):
        return

    core_v1.delete_namespaced_service(name=name, namespace=NAMESPACE)


def create_service(name: str, target_name: str) -> None:
    """Create a Kubernetes service to expose a pod.

    Creates a service that routes TCP traffic on port 80 to port 8888 of pods
    matching the target app label.

    Args:
        name: The name of the service to create.
        target_name: The app label value of pods to target.
    Raises:
        ApiException: If an error occurs while creating the service.
    """
    if ping_resource('svc', name):
        logger.warning(f"Service {name} already exists in namespace {NAMESPACE}. Skipping creation.")
        return

    service = client.V1Service(
        metadata=client.V1ObjectMeta(
            name=name,
            namespace=NAMESPACE
        ),
        spec=client.V1ServiceSpec(
            selector={"app": target_name},
            ports=[client.V1ServicePort(
                protocol="TCP",
                port=80,
                target_port=8888
            )]
        )
    )

    core_v1.create_namespaced_service(
        namespace=NAMESPACE,
        body=service
    )


def get_namespace_resource_allocation() -> dict:
    """Calculate total resource requests for all pods in the namespace.

    Iterates through all pods and sums up CPU, memory, and GPU resource requests.
    Handles multiple unit formats (m for millicores, Mi/Gi for memory).

    NOTE:
        This is a proof-of-concept version. Production should use a metrics server like Prometheus
        for accurate real-time resource metrics.
    Returns:
        dict: Dictionary with keys 'cpu' (cores), 'memory' (GiB), and 'gpu' (count),
            each containing the total requested resources rounded to 2 decimal places.
    Raises:
        ApiException: If an error occurs while listing the pods.
    """
    pods = core_v1.list_namespaced_pod(namespace=NAMESPACE)
    total_cpu_requests = 0.0
    total_memory_requests = 0.0
    total_gpu_requests = 0.0

    for pod in pods.items:
        for container in pod.spec.containers:
            requests = getattr(getattr(container, 'resources', None), 'requests', None)
            if not requests:
                continue

            # Parse CPU requests
            if cpu_str := requests.get('cpu'):
                if str(cpu_str).endswith('m'):
                    total_cpu_requests += int(str(cpu_str)[:-1]) / 1000
                else:
                    total_cpu_requests += float(cpu_str)

            # Parse memory requests
            if mem_str := requests.get('memory'):
                mem_str = str(mem_str)
                if mem_str.endswith('Gi'):
                    total_memory_requests += float(mem_str[:-2])
                elif mem_str.endswith('G'):
                    total_memory_requests += float(mem_str[:-1])
                elif mem_str.endswith('Mi'):
                    total_memory_requests += float(mem_str[:-2]) / 1024
                elif mem_str.endswith('M'):
                    total_memory_requests += float(mem_str[:-1]) / 1024

            # Parse GPU requests
            if gpu_str := requests.get(GPU_TYPE):
                try:
                    total_gpu_requests += float(gpu_str)
                except Exception:
                    pass

    return {
        'cpu': round(total_cpu_requests, 2),
        'memory': round(total_memory_requests, 2),
        'gpu': round(total_gpu_requests, 2)
    }


def get_pod_status(name: str) -> PodStatus:
    """Get the current status of a pod.

    Args:
        name: The name of the pod.
    Returns:
        PodStatus: The current status (RUNNING, PENDING, TERMINATED, ERROR, DOWN, TERMINATING, or UNKNOWN).
    """
    try:
        pod = core_v1.read_namespaced_pod(name=name, namespace=NAMESPACE)

        if pod.metadata.deletion_timestamp:
            return PodStatus.TERMINATING

        phase = pod.status.phase

        if phase == "Running":
            # Check if all containers are ready
            if pod.status.container_statuses:
                all_ready = all(container.ready for container in pod.status.container_statuses)
                return PodStatus.RUNNING if all_ready else PodStatus.PENDING
            return PodStatus.RUNNING
        elif phase == "Succeeded":
            return PodStatus.TERMINATED
        elif phase == "Failed":
            return PodStatus.ERROR
        elif phase == "Pending":
            return PodStatus.PENDING
        else:
            return PodStatus.UNKNOWN

    except ApiException as e:
        return PodStatus.DOWN if e.status == 404 else PodStatus.ERROR


def get_job_status(name: str) -> JobStatus:
    """Get the current status of a job.

    Args:
        name: The name of the job.
    Returns:
        JobStatus: The current status (RUNNING, PENDING, TERMINATED, ERROR, or UNKNOWN).
    """
    try:
        job = batch_v1.read_namespaced_job(name=name, namespace=NAMESPACE)

        if job.status.conditions:
            for condition in job.status.conditions:
                if condition.type == "Complete" and condition.status == "True":
                    return JobStatus.TERMINATED
                elif condition.type == "Failed" and condition.status == "True":
                    return JobStatus.ERROR

        if job.status.succeeded and job.status.succeeded > 0:
            return JobStatus.TERMINATED
        elif job.status.failed and job.status.failed > 0:
            return JobStatus.ERROR
        elif job.status.active and job.status.active > 0:
            return JobStatus.RUNNING
        else:
            return JobStatus.PENDING

    except ApiException as e:
        if e.status == 404:
            return JobStatus.UNKNOWN
        return JobStatus.ERROR


def wait_for_job(name: str, on_success: Callable[[], None], on_error: Callable[[Exception], None], timeout: int = 60) -> None:
    """Wait for a Kubernetes job to complete asynchronously and execute callbacks.

    Spawns a daemon thread that polls the job status every 2 seconds until completion,
    failure, or timeout. Executes the appropriate callback based on the outcome.

    Args:
        name: Name of the job to wait for.
        on_success: Callback function to invoke when the job completes successfully.
        on_error: Callback function to invoke with the exception when the job fails or times out.
        timeout: Maximum time to wait in seconds (default: 60).
    """
    import time
    
    def wait_and_callback():
        try:
            start_time = time.time()
            while time.time() - start_time < timeout:
                status = get_job_status(name)
                if status == JobStatus.TERMINATED:
                    on_success()
                    return
                elif status == JobStatus.ERROR:
                    raise RuntimeError(f"Job {name} failed")
                time.sleep(2)
            
            raise RuntimeError(f"Job {name} timed out after {timeout}s")
        except Exception as e:
            on_error(e)
    
    thread = threading.Thread(target=wait_and_callback, daemon=True)
    thread.start()
