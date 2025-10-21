import logging
import threading
from typing import Callable
from kubernetes import client, config  # type: ignore
from kubernetes.client.rest import ApiException  # type: ignore

from enums import PodStatus, JobStatus
from config import GPU_TYPE, NOTEBOOK_IMAGE, GMX_IMAGE, S3_CLIENT_IMAGE, S3_ACCESS_KEY, S3_SECRET_KEY, S3_ENDPOINT, S3_BUCKET, NAMESPACE


logger = logging.getLogger(__name__)


config.load_incluster_config()
core_v1 = client.CoreV1Api()
batch_v1 = client.BatchV1Api()


def get_container(
    name: str,
    image: str,
    experiment_id: str,
    mddash_volume: str,
    command: list[str],
    env: list[dict] | None = None,
    set_working_dir: bool = True,
    resources: dict | None = None,
) -> dict:
    """
    Get a generic container mounted to `mddash_volume` and started in `/mddash/{experiment_id}`.

    :param name: The name of the container.
    :param image: The container image to use.
    :param experiment_id: The ID of the experiment needed to set the working directory.
    :param mddash_volume: The name of the volume /mddash is mounted to.
    :param command: The command to run in the container.
    :param env: Optional list of environment variables to set in the container.
    :param set_working_dir: Whether to set the working directory to `/mddash/{experiment_id}`.
    :param resources: Optional resource requests/limits. If None, uses default (100m CPU, 128Mi memory).
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
        'imagePullPolicy': 'Always',  # TODO. maybe IfNotPresent?
        'resources': resources or {
            'requests': {'cpu': '100m', 'memory': '128Mi'},
            'limits': {'cpu': '200m', 'memory': '256Mi'}
        },
        'command': command,
        'volumeMounts': [
            {'mountPath': '/mddash', 'name': mddash_volume}
        ]
    }

    if set_working_dir:
        container['workingDir'] = f'/mddash/{experiment_id}'

    if env:
        container['env'] = env

    return container


def get_s3_init_container(experiment_id: str, mddash_volume: str) -> dict:
    """
    Get container that initializes the /mddash volume by downloading existing data from S3.

    :param experiment_id: The ID of the experiment needed to set the working directory.
    :param mddash_volume: The name of the volume /mddash is mounted to.
    """

    s3_init_command = f"""
        mkdir -p /tmp/.config/rclone &&
        cat > /tmp/.config/rclone/rclone.conf << EOF
[s3remote]
type = s3
provider = Other
access_key_id = $S3_ACCESS_KEY
secret_access_key = $S3_SECRET_KEY
endpoint = $S3_ENDPOINT
EOF
    mkdir -p /mddash/{experiment_id} &&
    echo "Syncing notebooks from s3remote:{S3_BUCKET}/{experiment_id}" &&
    rclone sync --config /tmp/.config/rclone/rclone.conf s3remote:{S3_BUCKET}/{experiment_id}/ /mddash/{experiment_id}/ --progress || echo "No existing data found, starting with empty directory"
    """

    env = [
        {
            'name': 'S3_ENDPOINT',
            'value': S3_ENDPOINT or ''
        },
        {
            'name': 'S3_ACCESS_KEY',
            'value': S3_ACCESS_KEY or ''
        },
        {
            'name': 'S3_SECRET_KEY',
            'value': S3_SECRET_KEY or ''
        }
    ]

    # Create s3-init container that runs as user 1000, permissions handled by fsGroup
    return get_container(
        's3-init',
        S3_CLIENT_IMAGE,
        experiment_id,
        mddash_volume,
        ['sh', '-c', s3_init_command],
        env,
        set_working_dir=False
    )


def get_s3_sync_container(experiment_id: str, mddash_volume: str) -> dict:
    """
    Get container that continuously syncs /mddash volume to S3 and performs a final sync on termination.

    NOTE: This container relies on the main container to create a file /mddash/.terminated after it has finished its work.

    :param experiment_id: The ID of the experiment needed to set the working directory.
    :param mddash_volume: The name of the volume /mddash is mounted to.
    """

    s3_sync_command = f"""
        export HOME=/tmp &&
        mkdir -p /tmp/.config/rclone &&
        cat > /tmp/.config/rclone/rclone.conf << EOF
[s3remote]
type = s3
provider = Other
access_key_id = $S3_ACCESS_KEY
secret_access_key = $S3_SECRET_KEY
endpoint = $S3_ENDPOINT
EOF
        while true; do
            if [ -f "/mddash/.terminated" ]; then
                sleep 2 &&
                # Final sync to S3
                rclone sync --config /tmp/.config/rclone/rclone.conf /mddash/{experiment_id}/ s3remote:{S3_BUCKET}/{experiment_id}/ --exclude "*.tmp" --exclude "*.lock" --log-level ERROR --retries 5 &&
                break
            fi

            # Periodic sync to S3 (make S3 match local, including deletions)
            rclone sync --config /tmp/.config/rclone/rclone.conf /mddash/{experiment_id}/ s3remote:{S3_BUCKET}/{experiment_id}/ --exclude "*.tmp" --exclude "*.lock" --log-level ERROR --retries 2 || echo "Upload sync failed" &&
            sleep 10
        done
    """

    env = [
        {
            'name': 'S3_ENDPOINT',
            'value': S3_ENDPOINT or ''
        },
        {
            'name': 'S3_ACCESS_KEY',
            'value': S3_ACCESS_KEY or ''
        },
        {
            'name': 'S3_SECRET_KEY',
            'value': S3_SECRET_KEY or ''
        }
    ]

    return get_container('s3-sync', S3_CLIENT_IMAGE, experiment_id, mddash_volume, ['sh', '-c', s3_sync_command], env)


def create_notebook_pod(name: str, experiment_id: str, prefix: str, token: str) -> None:
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

    mddash_volume = 'shared-data'
    workdir_init_container = get_container(
        'workdir-init',
        NOTEBOOK_IMAGE,
        experiment_id,
        mddash_volume,
        ['sh', '-c', workdir_init_command],
        set_working_dir=False
    )
    gmx_container = get_container('gmx', GMX_IMAGE, experiment_id, mddash_volume, ['sleep', '365d'])
    s3_init_container = get_s3_init_container(experiment_id, mddash_volume)
    s3_sync_container = get_s3_sync_container(experiment_id, mddash_volume)
    
    jupyter_command = ['sh', '-c',
        f'trap "echo \\"Container terminated at $(date)\\" > /mddash/.terminated" EXIT TERM INT; '
        f'start-notebook.sh '
        f'--NotebookApp.base_url={prefix} '
        f'--NotebookApp.notebook_dir=/mddash/{experiment_id} '
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
        mddash_volume,
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
                s3_init_container,
                workdir_init_container
            ],
            'containers': [
                jupyter_container,
                gmx_container,
                s3_sync_container
            ],
            'volumes': [
                {
                    'name': mddash_volume,
                    'emptyDir': {
                        'sizeLimit': '50Gi'  # TODO: adjust size limit to our needs
                    }
                }
            ]
        }
    }

    core_v1.create_namespaced_pod(namespace=NAMESPACE, body=pod_manifest)


def create_job(name: str, image: str, experiment_id: str, command: str) -> None:
    """
    Create a job that runs a given command in the `/mddash/{experiment_id}` directory.
    It is automatically synced to S3.

    :param name: The name of the job.
    :param image: The container image to use.
    :param experiment_id: The ID of the experiment needed to set the working directory.
    :param command: The command to run in the job. (wrapped inside `sh -c`)
    """

    if ping_resource('job', name):
        logger.warning(f"Job {name} already exists in namespace {NAMESPACE}. Skipping creation.")
        return

    mddash_volume = 'shared-data'

    # Wrap the command to create a /mddash/.terminated file on exit
    trapped_command = ['sh', '-c',
        f'trap "touch /mddash/.terminated" EXIT TERM INT; {command}'
    ]

    job_container = get_container(name, image, experiment_id, mddash_volume, trapped_command)
    s3_init_container = get_s3_init_container(experiment_id, mddash_volume)
    s3_sync_container = get_s3_sync_container(experiment_id, mddash_volume)

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
                    'initContainers': [
                        s3_init_container
                    ],
                    'containers': [
                        job_container,
                        s3_sync_container
                    ],
                    'volumes': [
                        {
                            'name': mddash_volume,
                            'emptyDir': {
                                'sizeLimit': '50Gi'  # TODO: adjust based on our needs
                            }
                        }
                    ]
                }
            }
        }
    }

    batch_v1.create_namespaced_job(namespace=NAMESPACE, body=job_manifest)


def ping_resource(resource_type: str, name: str) -> bool:
    """
    Check if a given resource exists in the namespace.

    :param resource_type: The type of the resource (e.g., 'svc', 'pod', 'configmap', 'secret', 'pvc', 'job').
    :param name: The name of the resource.
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
    if not ping_resource('pod', name):
        return

    core_v1.delete_namespaced_pod(name=name, namespace=NAMESPACE)


def delete_job(name: str) -> None:
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
    if not ping_resource('svc', name):
        return

    core_v1.delete_namespaced_service(name=name, namespace=NAMESPACE)


def create_service(name: str, target_name: str) -> None:
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
    '''
    Get resource requests/limits for all pods in namespace

    NOTE: This is just a proof-of-concept version, later we will need some metrics server like Prometheus.
    '''
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
    """
    Wait for a K8s job to complete in a background thread, then call the appropriate callback.
    
    :param name: Name of the job to wait for
    :param on_success: Callback to call when the job completes successfully
    :param on_error: Callback to call when the job fails or times out
    :param timeout: Maximum time to wait in seconds
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
