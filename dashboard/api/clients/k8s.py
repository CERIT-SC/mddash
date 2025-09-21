import logging
from kubernetes import client, config  # type: ignore
from kubernetes.client.rest import ApiException  # type: ignore

from enums import PodStatus
from config import S3_ACCESS_KEY, S3_SECRET_KEY, S3_ENDPOINT, S3_BUCKET


logger = logging.getLogger(__name__)
GPU_TYPE = 'nvidia.com/mig-1g.10gb'

config.load_incluster_config()
core_v1 = client.CoreV1Api()
batch_v1 = client.BatchV1Api()


# TODO
#  Ensure your pod has a corresponding label, such as spec.template.metadata.labels.app: example-pod.

# XXX: hardcoded gromacs image

def create_notebook_pod(
    image: str,
    ns: str,
    name: str,
    experiment_id: str,
    prefix: str,
    token: str
) -> None:
    if ping_resource('pod', name, ns):
        logger.warning(f"Pod {name} already exists in namespace {ns}. Skipping creation.")
        return

    # S3 sync commands using rclone
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
        echo "Downloading experiment data from s3remote:{S3_BUCKET}/{experiment_id}..." &&
        mkdir -p /mddash/{experiment_id} &&
        rclone sync --config /tmp/.config/rclone/rclone.conf s3remote:{S3_BUCKET}/{experiment_id}/ /mddash/{experiment_id}/ --progress || echo "No existing data found, starting with empty directory"
    """

    workdir_init_command = f"""
        echo "Initializing notebook templates..." &&
        # Check if any .ipynb files exist before trying to copy them
        if ls /home/jovyan/*.ipynb 1> /dev/null 2>&1; then
            echo "Found notebook templates, copying to experiment directory..." &&
            for n in /home/jovyan/*.ipynb; do 
                b=$(basename "$n")
                if [ -f "/mddash/{experiment_id}/$b" ]; then
                    echo "Template $b already exists, creating .new version" &&
                    cp "$n" "/mddash/{experiment_id}/$b.new"
                else
                    echo "Copying template: $b" &&
                    cp "$n" "/mddash/{experiment_id}/$b"
                fi
            done
        else
            echo "No notebook templates found, skipping copy"
        fi &&
        echo "Notebook initialization complete"
    """

    s3_sync_command = f"""
        export HOME=/tmp &&
        mkdir -p /tmp/.config/rclone &&
        mkdir -p /tmp/.cache/rclone &&
        cat > /tmp/.config/rclone/rclone.conf << EOF
[s3remote]
type = s3
provider = Other
access_key_id = $S3_ACCESS_KEY
secret_access_key = $S3_SECRET_KEY
endpoint = $S3_ENDPOINT
EOF
        echo "Starting continuous rclone bisync process..." &&
        rclone bisync --config /tmp/.config/rclone/rclone.conf /mddash/{experiment_id}/ s3remote:{S3_BUCKET}/{experiment_id}/ --create-empty-src-dirs --resync --log-level ERROR &&
        while true; do
            # Check if notebook container is still running
            if ! pgrep -f "start-notebook.sh" > /dev/null; then
                echo "Notebook container stopped, performing final bisync..." &&
                rclone bisync --config /tmp/.config/rclone/rclone.conf /mddash/{experiment_id}/ s3remote:{S3_BUCKET}/{experiment_id}/ --create-empty-src-dirs --delete-during --log-level ERROR &&
                echo "Final bisync completed, exiting..." &&
                break
            fi
            # Regular bisync every 10 seconds
            rclone bisync --config /tmp/.config/rclone/rclone.conf /mddash/{experiment_id}/ s3remote:{S3_BUCKET}/{experiment_id}/ --create-empty-src-dirs --delete-during --log-level ERROR || echo "Bisync failed, retrying..." &&
            sleep 10
        done
    """

    # Define the pod specification
    pod_manifest = {
        'apiVersion': 'v1',
        'kind': 'Pod',
        'metadata': {
            'name': name,
            'namespace': ns,
            'labels': {
                'app': name
            }
        },
        'spec': {
            'securityContext': {
                'fsGroup': 1000,
                'runAsNonRoot': True,
                'allowPrivilegeEscalation': False,
                'seccompProfile': {
                    'type': 'RuntimeDefault'
                }
            },
            'initContainers': [
                {
                    'name': 's3-init',
                    'image': 'rclone/rclone:latest',
                    'command': ['sh', '-c', s3_init_command],
                    'securityContext': {
                        'runAsUser': 1000,
                        'runAsGroup': 1000,
                        'runAsNonRoot': True,
                        'seccompProfile': {
                            'type': 'RuntimeDefault'
                        },
                        'allowPrivilegeEscalation': False,
                        'capabilities': {
                            'drop': ['ALL']
                        }
                    },
                    'env': [
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
                    ],
                    'resources': {
                        'requests': {'cpu': '100m', 'memory': '256Mi'},
                        'limits': {'cpu': '500m', 'memory': '512Mi'}
                    },
                    'volumeMounts': [
                        {'mountPath': '/mddash', 'name': 'shared-data'}
                    ]
                },
                {
                    'securityContext': {
                        'runAsNonRoot': True,
                        'runAsUser': 1000,
                        'allowPrivilegeEscalation': False,
                        'capabilities': {
                            'drop': ['ALL']
                        }
                    },
                    'name': 'init-workdir',
                    'image': image,
                    'resources': {
                        'requests': {'cpu': '100m', 'memory': '256Mi'},
                        'limits': {'cpu': '500m', 'memory': '512Mi'}
                    },
                    'command': ['sh', '-c', workdir_init_command],
                    'volumeMounts': [
                        {'mountPath': '/mddash', 'name': 'shared-data'}
                    ]
                }
            ],
            'containers': [
                {
                    'securityContext': {
                        'runAsNonRoot': True,
                        'runAsUser': 1000,
                        'allowPrivilegeEscalation': False,
                        'capabilities': {
                            'drop': ['ALL']
                        }
                    },
                    'name': 'jupyter',
                    'image': image,
                    'imagePullPolicy': 'Always',
                    'resources': {
                        'requests': {'cpu': '100m', 'memory': '512Mi'},
                        'limits': {'cpu': '2000m', 'memory': '8Gi'}
                    },
                    'workingDir': f'/mddash/{experiment_id}',
                    'env': [
                        {'name': 'WORKDIR', 'value': f'/mddash/{experiment_id}'},
                    ],
                    'args': [
                        'start-notebook.sh',
                        f'--NotebookApp.base_url={prefix}',
                        f'--NotebookApp.notebook_dir=/mddash/{experiment_id}',
                        f'--NotebookApp.token="{token}"',
                    ],
                    'volumeMounts': [
                        {'mountPath': '/mddash', 'name': 'shared-data'}
                    ]
                },
                {
                    'securityContext': {
                        'runAsNonRoot': True,
                        'runAsUser': 1000,
                        'allowPrivilegeEscalation': False,
                        'capabilities': {
                            'drop': ['ALL']
                        }
                    },
                    'name': 'gmx',
                    'image': 'cerit.io/ljocha/gromacs:2024-3-plumed-2-10-afed-pytorch-model-cv-2',
                    'imagePullPolicy': 'Always',
                    'resources': {
                        'requests': {'cpu': '100m', 'memory': '512Mi'},
                        'limits': {'cpu': '2000m', 'memory': '8Gi'}
                    },
                    'workingDir': f'/mddash/{experiment_id}',
                    'args': [
                        'sleep',
                        '365d'
                    ],
                    'volumeMounts': [
                        {'mountPath': '/mddash', 'name': 'shared-data'}
                    ]
                },
                {
                    'name': 's3-sync',
                    'image': 'rclone/rclone:latest',
                    'command': ['sh', '-c', s3_sync_command],
                    'securityContext': {
                        'runAsUser': 1000,
                        'runAsGroup': 1000,
                        'runAsNonRoot': True,
                        'seccompProfile': {
                            'type': 'RuntimeDefault'
                        },
                        'allowPrivilegeEscalation': False,
                        'capabilities': {
                            'drop': ['ALL']
                        }
                    },
                    'env': [
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
                    ],
                    'resources': {
                        'requests': {
                            'cpu': '100m',
                            'memory': '128Mi'
                        },
                        'limits': {
                            'cpu': '200m',
                            'memory': '256Mi'
                        }
                    },
                    'volumeMounts': [
                        {'name': 'shared-data', 'mountPath': '/mddash'}
                    ]
                }
            ],
            'volumes': [
                {
                    'name': 'shared-data',
                    'emptyDir': {
                        'sizeLimit': '50Gi'  # TODO: adjust size limit to our needs
                    }
                }
            ]
        }
    }

    core_v1.create_namespaced_pod(namespace=ns, body=pod_manifest)


def ping_resource(resource_type: str, name: str, ns: str) -> bool:
    try:
        match resource_type:
            case 'svc':
                core_v1.read_namespaced_service(name=name, namespace=ns)
            case 'pod':
                core_v1.read_namespaced_pod(name=name, namespace=ns)
            case 'configmap':
                core_v1.read_namespaced_config_map(name=name, namespace=ns)
            case 'secret':
                core_v1.read_namespaced_secret(name=name, namespace=ns)
            case 'pvc':
                core_v1.read_namespaced_persistent_volume_claim(
                    name=name, namespace=ns)
            case 'job':
                batch_v1.read_namespaced_job(name=name, namespace=ns)
            case _:
                raise ValueError(f"Unsupported resource type: {resource_type}")
        return True
    except ApiException as e:
        return False


def delete_pod(ns: str, name: str) -> None:
    if not ping_resource('pod', name, ns):
        return

    core_v1.delete_namespaced_pod(name=name, namespace=ns)


def delete_service(ns: str, name: str) -> None:
    if not ping_resource('svc', name, ns):
        return

    core_v1.delete_namespaced_service(name=name, namespace=ns)


def create_service(ns: str, name: str, target_name: str) -> None:
    if ping_resource('svc', name, ns):
        logger.warning(f"Service {name} already exists in namespace {ns}. Skipping creation.")
        return

    service = client.V1Service(
        metadata=client.V1ObjectMeta(
            name=name,
            namespace=ns
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
        namespace=ns,
        body=service
    )


def get_namespace_resource_allocation(ns: str) -> dict:
    '''
    Get resource requests/limits for all pods in namespace

    NOTE: This is just a proof-of-concept version, later we will need some metrics server like Prometheus.
    '''
    pods = core_v1.list_namespaced_pod(namespace=ns)
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


def get_pod_status(ns: str, name: str) -> PodStatus:    
    try:
        pod = core_v1.read_namespaced_pod(name=name, namespace=ns)

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
