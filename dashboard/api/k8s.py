from kubernetes import client, config
from kubernetes.client.rest import ApiException

# TODO
#  Ensure your pod has a corresponding label, such as spec.template.metadata.labels.app: example-pod.

# XXX: hardcoded gromacs image

def create_notebook_pod(image, ns, id, prefix, token):
    # Load in-cluster config
    config.load_incluster_config()

    # Define API client
    v1 = client.CoreV1Api()

    # Define the pod specification
    pod_manifest = {
        'apiVersion': 'v1',
        'kind': 'Pod',
        'metadata': {
            'name': f'jupyter-{id}',
            'namespace': ns,
            'labels': {
                'app': f'jupyter-{id}'
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
                    'command' : ['sh', '-c', f'''
for n in /home/jovyan/*.ipynb; do 
    b=$(basename "$n")
    if [ -f "/mddash/{id}/$b" ]; then
        cp "$n" "/mddash/{id}/$b.new"
    else
        cp "$n" "/mddash/{id}/$b"
    fi
done
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
                        'requests': {'cpu': .1, 'memory': '2Gi'},
                        'limits': {'cpu': 2, 'memory': '8Gi'}
                    },
                    'workdir': f'/mddash/{id}',
                    'env': [
                        { 'name' : 'WORKDIR', 'value' : f'/mddash/{id}' },
                    ],
                    'args': [
                        'start-notebook.sh',
                        f'--NotebookApp.base_url={prefix}',
                        f'--NotebookApp.notebook_dir=/mddash/{id}',
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
                        'requests' : { 'cpu': .1, 'memory': '2Gi' }, 
                        'limits' : { 'cpu': 2, 'memory' : '8Gi' }
                    },
                    'workdir': f'/mddash/{id}',
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
                    'persistentVolumeClaim': {'claimName': 'mddash-data'}
                }
            ]
        }
    }

    v1.create_namespaced_pod(namespace=ns, body=pod_manifest)
    # except ApiException as e:


def ping_resource(resource_type, name, ns):
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


def delete_notebook_pod(ns, id):
    if not ping_resource('pod', f'jupyter-{id}', ns):
        return

    config.load_incluster_config()
    api = client.CoreV1Api()
    api.delete_namespaced_pod(name='jupyter-'+id, namespace=ns)


def delete_notebook_service(ns, id):
    if not ping_resource('svc', f'svc-{id}', ns):
        return

    config.load_incluster_config()
    api = client.CoreV1Api()
    api.delete_namespaced_service(name='svc-'+id, namespace=ns)


def create_notebook_service(ns, id):
    config.load_incluster_config()

    service = client.V1Service(
        metadata=client.V1ObjectMeta(
            name=f'svc-{id}',
            namespace=ns
        ),
        spec=client.V1ServiceSpec(
            selector={"app": f"jupyter-{id}"},
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


def get_namespace_resource_allocation(ns):
    '''
    Get resource requests/limits for all pods in namespace

    NOTE: This is just a proof-of-concept version, later we will need some metrics server like Prometheus.
    '''
    config.load_incluster_config()
    api = client.CoreV1Api()

    try:
        pods = api.list_namespaced_pod(namespace=ns)
        total_cpu_requests = 0
        total_memory_requests = 0

        for pod in pods.items:
            for container in pod.spec.containers:
                if container.resources and container.resources.requests:
                    # Parse CPU requests
                    if 'cpu' in container.resources.requests:
                        cpu_str = container.resources.requests['cpu']
                        if cpu_str.endswith('m'):
                            total_cpu_requests += int(cpu_str[:-1]) / 1000
                        else:
                            total_cpu_requests += float(cpu_str)

                    # Parse memory requests
                    if 'memory' in container.resources.requests:
                        mem_str = container.resources.requests['memory']
                        if mem_str.endswith('Gi'):
                            total_memory_requests += float(mem_str[:-2])
                        elif mem_str.endswith('Mi'):
                            total_memory_requests += float(mem_str[:-2]) / 1024

        return {
            'cpu': round(total_cpu_requests, 3),
            'memory': round(total_memory_requests, 2),
            'gpu': 0
        }
    except Exception as e:
        print(f"Error: {e}")
        return {'cpu': 0, 'memory': 0, 'gpu': 0}


def create_gromacs_job(ns: str, name: str, experiment_id: str, tpr_name: str, np: int, ntomp: int, nb: str, pme: str, extra_args: str):
    config.load_incluster_config()
    batch_v1 = client.BatchV1Api()

    np = int(np)
    ntomp = int(ntomp)
    nb = nb.lower()
    pme = pme.lower()

    image = 'cerit.io/ljocha/gromacs:2024-3-plumed-2-10-afed-pytorch-model-cv-2'

    command = f"mpirun -np {np} gmx mdrun -ntomp {ntomp} -nb {nb} -pme {pme} -deffnm {tpr_name.strip('.tpr')} {extra_args} >{name}.out 2>{name}.err"

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
                                    'nvidia.com/mig-1g.10gb': '1' if nb == 'gpu' or pme == 'gpu' else '0'
                                },
                                'limits': {
                                    'cpu': str(np * ntomp),
                                    'memory': f'{4 * np}Gi',
                                    'nvidia.com/mig-1g.10gb': '1' if nb == 'gpu' or pme == 'gpu' else '0'
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
                                'claimName': 'mddash-data'
                            }
                        }
                    ]
                }
            }
        }
    }

    batch_v1.create_namespaced_job(namespace=ns, body=job_manifest)


def delete_gromacs_job(ns: str, name: str):
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


def get_job_status(ns: str, name: str) -> str:
    config.load_incluster_config()
    batch_v1 = client.BatchV1Api()

    job = batch_v1.read_namespaced_job(name=name, namespace=ns)

    # Check for completion conditions first
    if job.status.conditions:
        for condition in job.status.conditions:
            if condition.type == "Complete" and condition.status == "True":
                return "TERMINATED"
            elif condition.type == "Failed" and condition.status == "True":
                return "ERROR"

    # Check numeric status fields
    if job.status.succeeded and job.status.succeeded > 0:
        return "TERMINATED"
    elif job.status.failed and job.status.failed > 0:
        return "ERROR"
    elif job.status.active and job.status.active > 0:
        return "RUNNING"
    else:
        return "PENDING"
