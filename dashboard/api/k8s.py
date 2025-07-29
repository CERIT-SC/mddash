import logging
from kubernetes import client, config  # type: ignore
from kubernetes.client.rest import ApiException  # type: ignore

from k8s_status import JobStatus, PodStatus


logger = logging.getLogger(__name__)
GPU_TYPE = 'nvidia.com/mig-1g.10gb'


# TODO
#  Ensure your pod has a corresponding label, such as spec.template.metadata.labels.app: example-pod.

# XXX: hardcoded gromacs image

def create_notebook_pod(
    image: str,
    ns: str,
    pvc: str,
    name: str,
    experiment_id: str,
    prefix: str,
    token: str
) -> None:
    if ping_resource('pod', name, ns):
        logger.warning(f"Pod {name} already exists in namespace {ns}. Skipping creation.")
        return

    # Load in-cluster config
    config.load_incluster_config()

    # Define API client
    v1 = client.CoreV1Api()

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
                'runAsNonRoot': True,
                'allowPrivilegeEscalation': False,
                'seccompProfile': {
                    'type': 'RuntimeDefault'
                }
            },
            'initContainers': [
                {
                    'securityContext': {
                        'runAsNonRoot' : True,
                        'runAsUser': 1000,
                        'allowPrivilegeEscalation': False,
                        'capabilities':  {
                            'drop': [ 'ALL' ]
                        }
                    },
                    'name' : 'init-workdir',
                    'image': image,
                    'resources': {
                        'requests': { 'cpu': '100m', 'memory': '256Mi' },
                        'limits':   { 'cpu': '500m', 'memory': '512Mi' }
                    },
                    'command' : ['sh', '-c', f'''
mkdir -p "/mddash/{experiment_id}"
# Check if any .ipynb files exist before trying to copy them
if ls /home/jovyan/*.ipynb 1> /dev/null 2>&1; then
    for n in /home/jovyan/*.ipynb; do 
        b=$(basename "$n")
        if [ -f "/mddash/{experiment_id}/$b" ]; then
            cp "$n" "/mddash/{experiment_id}/$b.new"
        else
            cp "$n" "/mddash/{experiment_id}/$b"
        fi
    done
else
    echo "No .ipynb files found in /home/jovyan/, skipping copy"
fi
'''
                    ],
                    'volumeMounts' : [
                        { 'mountPath': '/mddash', 'name' : 'data-volume' }
                    ]
                }
             ],
            'containers': [
                {
                    'securityContext': {
                        'runAsNonRoot' : True,
                        'runAsUser': 1000,
                        'allowPrivilegeEscalation': False,
                        'capabilities':  {
                            'drop': ['ALL']
                        }
                    },
                    'name': f'jupyter',
                    'image': image,
                    'imagePullPolicy': 'Always',
                    'resources': {
                        'requests': {'cpu': '100m', 'memory': '512Mi'},
                        'limits': {'cpu': '2000m', 'memory': '8Gi'}
                    },
                    'workdir': f'/mddash/{experiment_id}',
                    'env': [
                        { 'name' : 'WORKDIR', 'value' : f'/mddash/{experiment_id}' },
                    ],
                    'args': [
                        'start-notebook.sh',
                        f'--NotebookApp.base_url={prefix}',
                        f'--NotebookApp.notebook_dir=/mddash/{experiment_id}',
                        f'--NotebookApp.token="{token}"',
                    ],
                    'volumeMounts': [
                        {'mountPath': '/mddash', 'name': 'data-volume'}
                    ]
                },
                {
                    'securityContext': {
                        'runAsNonRoot' : True,
                        'runAsUser': 1000,
                        'allowPrivilegeEscalation': False,
                        'capabilities':  {
                            'drop': [ 'ALL' ]
                        }
                    },
                    'name': f'gmx',
                    'image': 'cerit.io/ljocha/gromacs:2024-3-plumed-2-10-afed-pytorch-model-cv-2',
                    'imagePullPolicy': 'Always',
                    'resources': {
                        'requests' : { 'cpu': '100m', 'memory': '512Mi' }, 
                        'limits' : { 'cpu': '2000m', 'memory' : '8Gi' }
                    },
                    'workdir': f'/mddash/{experiment_id}',
                    'args': [
                        'sleep',
                        '365d'
                    ],
                    'volumeMounts' : [
                        { 'mountPath': '/mddash', 'name' : 'data-volume' }
                    ]
                }
            ],
            'volumes': [
                {
                    'name': 'data-volume',
                    'persistentVolumeClaim': {'claimName': pvc}
                }
            ]
        }
    }

    v1.create_namespaced_pod(namespace=ns, body=pod_manifest)
    # except ApiException as e:


def ping_resource(resource_type: str, name: str, ns: str) -> bool:
    config.load_incluster_config()
    api = client.CoreV1Api()

    try:
        match resource_type:
            case 'svc':
                api.read_namespaced_service(name=name, namespace=ns)
            case 'pod':
                api.read_namespaced_pod(name=name, namespace=ns)
            case 'configmap':
                api.read_namespaced_config_map(name=name, namespace=ns)
            case 'secret':
                api.read_namespaced_secret(name=name, namespace=ns)
            case 'pvc':
                api.read_namespaced_persistent_volume_claim(
                    name=name, namespace=ns)
            case 'job':
                batch_api = client.BatchV1Api()
                batch_api.read_namespaced_job(name=name, namespace=ns)
            case _:
                raise ValueError(f"Unsupported resource type: {resource_type}")
        return True
    except ApiException as e:
        return False


def delete_pod(ns: str, name: str) -> None:
    if not ping_resource('pod', name, ns):
        return

    config.load_incluster_config()
    api = client.CoreV1Api()
    api.delete_namespaced_pod(name=name, namespace=ns)


def delete_service(ns: str, name: str) -> None:
    if not ping_resource('svc', name, ns):
        return

    config.load_incluster_config()
    api = client.CoreV1Api()
    api.delete_namespaced_service(name=name, namespace=ns)


def create_service(ns: str, name: str, target_name: str) -> None:
    if ping_resource('svc', name, ns):
        logger.warning(f"Service {name} already exists in namespace {ns}. Skipping creation.")
        return

    config.load_incluster_config()

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

    api = client.CoreV1Api()
    api.create_namespaced_service(
        namespace=ns,
        body=service
    )


def get_namespace_resource_allocation(ns: str) -> dict:
    '''
    Get resource requests/limits for all pods in namespace

    NOTE: This is just a proof-of-concept version, later we will need some metrics server like Prometheus.
    '''
    config.load_incluster_config()
    api = client.CoreV1Api()
    pods = api.list_namespaced_pod(namespace=ns)
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


def create_gromacs_job(
    ns: str,
    pvc: str,
    name: str,
    experiment_id: str,
    deffnm: str,
    np: int,
    ntomp: int,
    nb: str,
    pme: str,
    extra_args: str
) -> None:
    if ping_resource('job', name, ns):
        logger.warning(f"Job {name} already exists in namespace {ns}. Skipping creation.")
        return

    config.load_incluster_config()
    batch_v1 = client.BatchV1Api()

    np = int(np)
    ntomp = int(ntomp)
    nb = nb.lower()
    pme = pme.lower()

    image = 'cerit.io/ljocha/gromacs:2024-3-plumed-2-10-afed-pytorch-model-cv-2'

    command = f"mpirun -np {np} gmx mdrun -ntomp {ntomp} -nb {nb} -pme {pme} -deffnm {deffnm} {extra_args} >{name}.out 2>{name}.err"

    job_manifest = {
        'apiVersion': 'batch/v1',
        'kind': 'Job',
        'metadata': {
            'name': name,
            'namespace': ns,
            'labels': {
                'app': name,
            }
        },
        'spec': {
            'backoffLimit': 0,
            'template': {
                'metadata': {
                    'labels': {
                        'job': name,
                    }
                },
                'spec': {
                    'restartPolicy': 'Never',
                    'containers': [
                        {
                            'name': name,
                            'image': image,
                            'workingDir': f'/mddash/{experiment_id}',
                            'command': ['bash', '-c', command],
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
                                    'name': 'OMP_NUM_THREADS',
                                    'value': str(ntomp)
                                }
                            ],
                            'resources': {
                                'requests': {
                                    'cpu': str(np * ntomp),
                                    'memory': f'{4 * np}Gi',
                                    GPU_TYPE: '1' if nb == 'gpu' or pme == 'gpu' else '0'
                                },
                                'limits': {
                                    'cpu': str(np * ntomp),
                                    'memory': f'{4 * np}Gi',
                                    GPU_TYPE: '1' if nb == 'gpu' or pme == 'gpu' else '0'
                                }
                            },
                            'volumeMounts': [
                                {
                                    'name': 'vol-1',
                                    'mountPath': '/mddash',
                                }
                            ]
                        }
                    ],
                    'volumes': [
                        {
                            'name': 'vol-1',
                            'persistentVolumeClaim': {
                                'claimName': pvc
                            }
                        }
                    ]
                }
            }
        }
    }

    batch_v1.create_namespaced_job(namespace=ns, body=job_manifest)


def delete_job(ns: str, name: str) -> None:
    if not ping_resource('job', name, ns):
        logger.warning(f"Job {name} does not exist in namespace {ns}. Skipping deletion.")
        return

    config.load_incluster_config()
    batch_v1 = client.BatchV1Api()
    batch_v1.delete_namespaced_job(
        name=name,
        namespace=ns,
        body=client.V1DeleteOptions(
            propagation_policy='Background',
            grace_period_seconds=5,
        )
    )


def get_job_status(ns: str, name: str) -> JobStatus:
    try:
        config.load_incluster_config()
        batch_v1 = client.BatchV1Api()
        job = batch_v1.read_namespaced_job(name=name, namespace=ns)

        # Check for completion conditions first
        if job.status.conditions:
            for condition in job.status.conditions:
                if condition.type == "Complete" and condition.status == "True":
                    return JobStatus.TERMINATED
                elif condition.type == "Failed" and condition.status == "True":
                    return JobStatus.ERROR

        # Check numeric status fields
        if job.status.succeeded and job.status.succeeded > 0:
            return JobStatus.TERMINATED
        elif job.status.failed and job.status.failed > 0:
            return JobStatus.ERROR
        elif job.status.active and job.status.active > 0:
            return JobStatus.RUNNING
        else:
            return JobStatus.PENDING

    except ApiException as e:
        return JobStatus.ERROR


def get_pod_status(ns: str, name: str) -> PodStatus:    
    try:
        config.load_incluster_config()
        v1 = client.CoreV1Api()
        pod = v1.read_namespaced_pod(name=name, namespace=ns)

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
