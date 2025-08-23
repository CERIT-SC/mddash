import logging
from kubernetes import client, config  # type: ignore
from kubernetes.client.rest import ApiException  # type: ignore

from enums import JobStatus

logger = logging.getLogger(__name__)
GPU_TYPE = 'nvidia.com/mig-1g.10gb'


def create_pvc(ns: str, pvc_name: str) -> None:
    """Ensure PVC exists in the given namespace, create if it doesn't exist."""
    if ping_resource('pvc', pvc_name, ns):
        logger.info(f"PVC {pvc_name} already exists in namespace {ns}")
        return
    
    config.load_incluster_config()
    api = client.CoreV1Api()
    
    pvc_manifest = {
        'apiVersion': 'v1',
        'kind': 'PersistentVolumeClaim',
        'metadata': {
            'name': pvc_name,
            'namespace': ns
        },
        'spec': {
            'accessModes': ['ReadWriteMany'],
            'storageClassName': 'nfs-csi',
            'resources': {
                'requests': {
                    'storage': '10Gi'
                }
            }
        }
    }
    
    api.create_namespaced_persistent_volume_claim(namespace=ns, body=pvc_manifest)
    logger.info(f"Created PVC {pvc_name} in namespace {ns}")


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
    command = f"pwd && ls -la /data && ls -la /data/{experiment_id} && mpirun -np {np} gmx mdrun -ntomp {ntomp} -nb {nb} -pme {pme} -deffnm {deffnm} {extra_args} >{name}.out 2>{name}.err"

    job_manifest = {
        'apiVersion': 'batch/v1',
        'kind': 'Job',
        'metadata': {
            'name': name,
            'namespace': ns,
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
                        {
                            'name': name,
                            'image': image,
                            'workingDir': f'/data/{experiment_id}',
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
                                    'mountPath': '/data',
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
    logger.info(f"Created GROMACS job {name} in namespace {ns}")


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
    logger.info(f"Deleted job {name} from namespace {ns}")


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
                api.read_namespaced_persistent_volume_claim(name=name, namespace=ns)
            case 'job':
                batch_api = client.BatchV1Api()
                batch_api.read_namespaced_job(name=name, namespace=ns)
            case _:
                raise ValueError(f"Unsupported resource type: {resource_type}")
        return True
    except ApiException as e:
        return False


def get_job_status(ns: str, name: str) -> JobStatus:
    try:
        config.load_incluster_config()
        batch_v1 = client.BatchV1Api()
        job = batch_v1.read_namespaced_job(name=name, namespace=ns)

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
