import logging
from kubernetes import client, config  # type: ignore
from kubernetes.client.rest import ApiException  # type: ignore

from enums import JobStatus
from config import S3_ACCESS_KEY, S3_SECRET_KEY, S3_ENDPOINT

logger = logging.getLogger(__name__)
GPU_TYPE = 'nvidia.com/mig-1g.10gb'


def ensure_s3_bucket(bucket_name: str) -> None:
    """S3 bucket operations are handled by the sidecar container."""
    logger.info(f"S3 bucket {bucket_name} will be accessed by sidecar container")


def create_gromacs_job(
    ns: str,
    bucket_name: str,
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

    gromacs_image = 'cerit.io/ljocha/gromacs:2024-3-plumed-2-10-afed-pytorch-model-cv-2'
    s3_sync_image = 'minio/mc:latest'  # TODO: lock version

    gromacs_command = f"mpirun -np {np} gmx mdrun -ntomp {ntomp} -nb {nb} -pme {pme} -deffnm {deffnm} {extra_args} >{name}.out 2>{name}.err && touch /data/job_completed"
    
    # S3 sync commands - download initially, then continuously sync with final sync on completion
    s3_init_command = f"""
        export MC_CONFIG_DIR=/tmp/.mc &&
        echo "Setting up S3 alias..." &&
        mc alias set s3 $S3_ENDPOINT $S3_ACCESS_KEY $S3_SECRET_KEY &&
        echo "Downloading experiment data..." &&
        mkdir -p /data/{experiment_id} &&
        mc mirror s3/{bucket_name}/{experiment_id}/ /data/{experiment_id}/
    """

    s3_sync_command = f"""
        export MC_CONFIG_DIR=/tmp/.mc &&
        mc alias set s3 $S3_ENDPOINT $S3_ACCESS_KEY $S3_SECRET_KEY &&
        echo "Starting continuous sync process..." &&
        while true; do
            # Check if main job is done
            if [ -f /data/job_completed ]; then
                echo "Job completed, performing final sync..." &&
                mc mirror --overwrite /data/{experiment_id}/ s3/{bucket_name}/{experiment_id}/ &&
                echo "Final sync completed, exiting..." &&
                break
            fi
            # Regular sync every 10 seconds
            mc mirror --overwrite /data/{experiment_id}/ s3/{bucket_name}/{experiment_id}/ 2>/dev/null || echo "Sync attempt failed, retrying..."
            sleep 10
        done
    """

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
                    'initContainers': [
                        {
                            'name': 's3-init',
                            'image': s3_sync_image,
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
                            'volumeMounts': [
                                {
                                    'name': 'shared-data',
                                    'mountPath': '/data'
                                }
                            ]
                        }
                    ],
                    'containers': [
                        {
                            'name': name,
                            'image': gromacs_image,
                            'workingDir': f'/data/{experiment_id}',
                            'command': ['bash', '-c', gromacs_command],
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
                                    'name': 'shared-data',
                                    'mountPath': '/data'
                                }
                            ]
                        },
                        {
                            'name': 's3-sync',
                            'image': s3_sync_image,
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
                                {
                                    'name': 'shared-data',
                                    'mountPath': '/data'
                                }
                            ]
                        }
                    ],
                    'volumes': [
                        {
                            'name': 'shared-data',
                            'emptyDir': {
                                'sizeLimit': '100Gi'  # Adjust based on your needs
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
