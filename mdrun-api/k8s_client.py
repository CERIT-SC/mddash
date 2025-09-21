import logging
from kubernetes import client, config  # type: ignore
from kubernetes.client.rest import ApiException  # type: ignore

from enums import JobStatus
from config import S3_ACCESS_KEY, S3_SECRET_KEY, S3_ENDPOINT

logger = logging.getLogger(__name__)
GPU_TYPE = 'nvidia.com/mig-1g.10gb'

config.load_incluster_config()
core_v1 = client.CoreV1Api()
batch_v1 = client.BatchV1Api()


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

    np = int(np)
    ntomp = int(ntomp)
    nb = nb.lower()
    pme = pme.lower()

    gromacs_image = 'cerit.io/ljocha/gromacs:2024-3-plumed-2-10-afed-pytorch-model-cv-2'
    s3_sync_image = 'rclone/rclone:latest'  # TODO: lock version

    gromacs_command = f"""
        trap 'touch /data/job_completed' EXIT
        mpirun -np {np} gmx mdrun -ntomp {ntomp} -nb {nb} -pme {pme} -deffnm {deffnm} {extra_args} > >(tee {name}.out) 2> >(tee {name}.err >&2)
    """

    # S3 sync commands using rclone - download initially, then continuously sync with final sync on completion
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
        echo "Downloading experiment data from s3remote:{bucket_name}/{experiment_id}..." &&
        mkdir -p /data/{experiment_id} &&
        rclone sync --config /tmp/.config/rclone/rclone.conf s3remote:{bucket_name}/{experiment_id}/ /data/{experiment_id}/ --progress || echo "No existing data found, starting with empty directory"
    """

    s3_sync_command = f"""
        mkdir -p /tmp/.config/rclone &&
        cat > /tmp/.config/rclone/rclone.conf << EOF
[s3remote]
type = s3
provider = Other
access_key_id = $S3_ACCESS_KEY
secret_access_key = $S3_SECRET_KEY
endpoint = $S3_ENDPOINT
EOF
        echo "Starting continuous rclone sync process..." &&
        while true; do
            # Check if main job is done
            if [ -f /data/job_completed ]; then
                echo "Job completed, performing final sync..." &&
                rclone sync --config /tmp/.config/rclone/rclone.conf /data/{experiment_id}/ s3remote:{bucket_name}/{experiment_id}/ --checksum --progress &&
                echo "Final sync completed, exiting..." &&
                break
            fi
            # Regular sync every 10 seconds - allow syncing of changing files
            rclone sync --config /tmp/.config/rclone/rclone.conf /data/{experiment_id}/ s3remote:{bucket_name}/{experiment_id}/ --ignore-checksum --retries 1 --quiet || echo "Sync attempt failed, retrying..."
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
                                'sizeLimit': '100Gi'  # TODO: adjust based on our needs
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
                core_v1.read_namespaced_persistent_volume_claim(name=name, namespace=ns)
            case 'job':
                batch_v1.read_namespaced_job(name=name, namespace=ns)
            case _:
                raise ValueError(f"Unsupported resource type: {resource_type}")
        return True
    except ApiException as e:
        return False


def get_job_status(ns: str, name: str) -> JobStatus:
    try:
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
