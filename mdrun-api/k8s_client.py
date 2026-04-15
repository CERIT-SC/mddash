import logging
import shlex
from http import HTTPStatus
from typing import TYPE_CHECKING, cast

from config import AMBER_IMAGE, GMX_IMAGE, GPU_TYPE, S3_ACCESS_KEY, S3_ENDPOINT, S3_SECRET_KEY
from enums import JobStatus
from kubernetes import client, config
from kubernetes.client.rest import ApiException

if TYPE_CHECKING:
    from kubernetes.client import V1Job


logger = logging.getLogger(__name__)

config.load_incluster_config()
core_v1 = client.CoreV1Api()
batch_v1 = client.BatchV1Api()


def _q(value: str) -> str:
    return shlex.quote(value)


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
    extra_args: str,
) -> None:
    """
    Create a GROMACS MD simulation job in Kubernetes.

    Args:
        ns: Kubernetes namespace for the job.
        bucket_name: S3 bucket name for data storage.
        name: Unique name for the Kubernetes job.
        experiment_id: Experiment identifier for data organization.
        deffnm: GROMACS default filename prefix (without .tpr extension).
        np: Number of MPI processes.
        ntomp: Number of OpenMP threads per process.
        nb: Non-bonded interaction device type ('cpu' or 'gpu').
        pme: PME calculation device type ('cpu' or 'gpu').
        extra_args: Additional arguments to pass to gmx mdrun.
    """
    if ping_resource("job", name, ns):
        logger.warning(f"Job {name} already exists in namespace {ns}. Skipping creation.")
        return

    np = int(np)
    ntomp = int(ntomp)
    nb = nb.lower()
    pme = pme.lower()

    exp_dir = f"/data/{experiment_id}"
    exp_dir_q = _q(f"{exp_dir}/")
    remote_q = _q(f"s3remote:{bucket_name}/{experiment_id}/")

    extra_part = f" {extra_args}" if extra_args else ""

    gromacs_image = GMX_IMAGE
    s3_sync_image = "rclone/rclone:latest"  # TODO: lock version

    # Rclone env-var based config (no config file needed)
    rclone_env = [
        {"name": "RCLONE_CONFIG_S3REMOTE_TYPE", "value": "s3"},
        {"name": "RCLONE_CONFIG_S3REMOTE_PROVIDER", "value": "Other"},
        {"name": "RCLONE_CONFIG_S3REMOTE_ACCESS_KEY_ID", "value": S3_ACCESS_KEY or ""},
        {"name": "RCLONE_CONFIG_S3REMOTE_SECRET_ACCESS_KEY", "value": S3_SECRET_KEY or ""},
        {"name": "RCLONE_CONFIG_S3REMOTE_ENDPOINT", "value": S3_ENDPOINT or ""},
    ]

    gromacs_command = "\n".join([
        "set -euo pipefail",
        "trap 'touch /data/job_completed' EXIT TERM INT",
        (
            " ".join([
                "mpirun",
                "-np",
                str(np),
                "gmx",
                "mdrun",
                "-ntomp",
                str(ntomp),
                "-nb",
                _q(nb),
                "-pme",
                _q(pme),
                "-deffnm",
                _q(deffnm),
            ])
            + extra_part
            + f" > >(tee {_q(f'{name}.out')}) 2> >(tee {_q(f'{name}.err')} >&2)"
        ),
        "echo 'Processing trajectory for visualization...'",
        f"gmx select -s {_q(f'{deffnm}.gro')} -on {_q(f'{deffnm}.p.ndx')} -select Protein",
        (
            f"gmx trjconv -s {_q(f'{deffnm}.gro')} -f {_q(f'{deffnm}.xtc')} -o {_q(f'{deffnm}.pbc.xtc')} "
            f"-pbc nojump -n {_q(f'{deffnm}.p.ndx')}"
        ),
        (
            f"gmx trjconv -s {_q(f'{deffnm}.gro')} -f {_q(f'{deffnm}.pbc.xtc')} -o {_q(f'{deffnm}.fit.xtc')} "
            f"-fit rot+trans -n {_q(f'{deffnm}.p.ndx')}"
        ),
        f"rm -f {_q(f'{deffnm}.p.ndx')} {_q(f'{deffnm}.pbc.xtc')}",
        "echo 'Trajectory processing completed.'",
    ])

    # Download experiment data from S3 before the simulation starts
    s3_init_command = f"""
        echo "Downloading experiment data from object storage..." &&
        mkdir -p {_q(exp_dir)} &&
        rclone copy {remote_q} {exp_dir_q} --progress || echo "No existing data found, starting with empty directory"
    """

    # Continuously upload results back to S3 while the job runs
    s3_sync_command = f"""
        echo "Starting continuous rclone copy process..." &&
        while true; do
            if [ -f /data/job_completed ]; then
                echo "Job completed, performing final copy to S3..." &&
                rclone copy {exp_dir_q} {remote_q} --checksum --progress &&
                echo "Final copy completed, exiting..." &&
                break
            fi
            rclone copy {exp_dir_q} {remote_q} --ignore-checksum --retries 1 --quiet || echo "Copy attempt failed, retrying..."
            sleep 10
        done
    """

    job_manifest = {
        "apiVersion": "batch/v1",
        "kind": "Job",
        "metadata": {"name": name, "namespace": ns, "labels": {"app": name}},
        "spec": {
            "backoffLimit": 0,
            "ttlSecondsAfterFinished": 3600,  # 1 hour
            "template": {
                "metadata": {"labels": {"job": name}},
                "spec": {
                    "restartPolicy": "Never",
                    "securityContext": {"fsGroup": 1000},
                    "initContainers": [
                        {
                            "name": "s3-init",
                            "image": s3_sync_image,
                            "command": ["sh", "-c", s3_init_command],
                            "securityContext": {
                                "runAsUser": 1000,
                                "runAsGroup": 1000,
                                "runAsNonRoot": True,
                                "seccompProfile": {"type": "RuntimeDefault"},
                                "allowPrivilegeEscalation": False,
                                "capabilities": {"drop": ["ALL"]},
                            },
                            "env": rclone_env,
                            "volumeMounts": [{"name": "shared-data", "mountPath": "/data"}],
                        }
                    ],
                    "containers": [
                        {
                            "name": name,
                            "image": gromacs_image,
                            "workingDir": exp_dir,
                            "command": ["bash", "-c", gromacs_command],
                            "securityContext": {
                                "runAsUser": 1000,
                                "runAsGroup": 1000,
                                "runAsNonRoot": True,
                                "seccompProfile": {"type": "RuntimeDefault"},
                                "allowPrivilegeEscalation": False,
                                "capabilities": {"drop": ["ALL"]},
                            },
                            "env": [{"name": "OMP_NUM_THREADS", "value": str(ntomp)}],
                            "resources": {
                                "requests": {
                                    "cpu": str(np * ntomp),
                                    "memory": f"{4 * np}Gi",
                                    GPU_TYPE: "1" if nb == "gpu" or pme == "gpu" else "0",
                                },
                                "limits": {
                                    "cpu": str(np * ntomp),
                                    "memory": f"{4 * np}Gi",
                                    GPU_TYPE: "1" if nb == "gpu" or pme == "gpu" else "0",
                                },
                            },
                            "volumeMounts": [{"name": "shared-data", "mountPath": "/data"}],
                        },
                        {
                            "name": "s3-sync",
                            "image": s3_sync_image,
                            "command": ["sh", "-c", s3_sync_command],
                            "securityContext": {
                                "runAsUser": 1000,
                                "runAsGroup": 1000,
                                "runAsNonRoot": True,
                                "seccompProfile": {"type": "RuntimeDefault"},
                                "allowPrivilegeEscalation": False,
                                "capabilities": {"drop": ["ALL"]},
                            },
                            "env": rclone_env,
                            "resources": {
                                "requests": {"cpu": "100m", "memory": "128Mi"},
                                "limits": {"cpu": "200m", "memory": "256Mi"},
                            },
                            "volumeMounts": [{"name": "shared-data", "mountPath": "/data"}],
                        },
                    ],
                    "volumes": [
                        {
                            "name": "shared-data",
                            "emptyDir": {
                                "sizeLimit": "100Gi"  # TODO: adjust based on our needs
                            },
                        }
                    ],
                },
            },
        },
    }

    batch_v1.create_namespaced_job(namespace=ns, body=job_manifest)
    logger.info(f"Created GROMACS job {name} in namespace {ns}")


def create_amber_job(
    ns: str,
    bucket_name: str,
    name: str,
    experiment_id: str,
    prmtop_name: str,
    inpcrd_name: str,
    mdin_name: str,
    binary: str,
    np: int,
    ntomp: int,
    ewald: str,
    extra_args: str,
) -> None:
    """
    Create an AMBER MD simulation job in Kubernetes.

    Args:
        ns: Kubernetes namespace for the job.
        bucket_name: S3 bucket name for data storage.
        name: Unique name for the Kubernetes job.
        experiment_id: Experiment identifier for data organization.
        prmtop_name: AMBER topology file name (relative path within experiment).
        inpcrd_name: AMBER coordinate file name (relative path within experiment).
        mdin_name: AMBER input file name (relative path within experiment).
        binary: AMBER binary type ('pmemd.cuda' or 'pmemd.MPI').
        np: Number of MPI processes (for pmemd.MPI).
        ntomp: Number of OpenMP threads per process.
        ewald: Ewald summation preset ('default' or 'optimized').
        extra_args: Additional arguments to pass to pmemd.
    """
    if ping_resource("job", name, ns):
        logger.warning(f"Job {name} already exists in namespace {ns}. Skipping creation.")
        return

    np = int(np)
    ntomp = int(ntomp)
    binary = binary.lower()
    ewald = ewald.lower()

    exp_dir = f"/data/{experiment_id}"
    exp_dir_q = _q(f"{exp_dir}/")
    remote_q = _q(f"s3remote:{bucket_name}/{experiment_id}/")

    # Output file prefix based on mdin filename stem
    output_prefix = Path(mdin_name).stem

    extra_part = f" {extra_args}" if extra_args else ""

    amber_image = AMBER_IMAGE
    s3_sync_image = "rclone/rclone:latest"

    # Rclone env-var based config (no config file needed)
    rclone_env = [
        {"name": "RCLONE_CONFIG_S3REMOTE_TYPE", "value": "s3"},
        {"name": "RCLONE_CONFIG_S3REMOTE_PROVIDER", "value": "Other"},
        {"name": "RCLONE_CONFIG_S3REMOTE_ACCESS_KEY_ID", "value": S3_ACCESS_KEY or ""},
        {"name": "RCLONE_CONFIG_S3REMOTE_SECRET_ACCESS_KEY", "value": S3_SECRET_KEY or ""},
        {"name": "RCLONE_CONFIG_S3REMOTE_ENDPOINT", "value": S3_ENDPOINT or ""},
    ]

    # Build AMBER command based on binary type
    base_flags = f"-O -i {_q(mdin_name)} -o {_q(f'{output_prefix}.out')} -p {_q(prmtop_name)} -c {_q(inpcrd_name)} -r {_q(f'{output_prefix}.rst7')} -x {_q(f'{output_prefix}.nc')}"

    if binary == "pmemd.cuda":
        # GPU binary: use CUDA_VISIBLE_DEVICES to control GPU visibility
        ewald_flag = "" if ewald == "default" else f" -ewald {ewald}"
        amber_command = "\n".join([
            "set -euo pipefail",
            "trap 'touch /data/job_completed' EXIT TERM INT",
            (
                " ".join([
                    "pmemd.cuda",
                    base_flags,
                    ewald_flag,
                ]).rstrip()
                + extra_part
                + f" > >(tee {_q(f'{name}.out')}) 2> >(tee {_q(f'{name}.err')} >&2)"
            ),
        ])
        use_gpu = True
    else:
        # MPI binary: use mpirun
        amber_command = "\n".join([
            "set -euo pipefail",
            "trap 'touch /data/job_completed' EXIT TERM INT",
            (
                " ".join([
                    "mpirun",
                    "-np",
                    str(np),
                    "pmemd.MPI",
                    base_flags,
                ])
                + extra_part
                + f" > >(tee {_q(f'{name}.out')}) 2> >(tee {_q(f'{name}.err')} >&2)"
            ),
        ])
        use_gpu = False

    # Download experiment data from S3 before the simulation starts
    s3_init_command = f"""
        echo "Downloading experiment data from object storage..." &&
        mkdir -p {_q(exp_dir)} &&
        rclone copy {remote_q} {exp_dir_q} --progress || echo "No existing data found, starting with empty directory"
    """

    # Continuously upload results back to S3 while the job runs
    s3_sync_command = f"""
        echo "Starting continuous rclone copy process..." &&
        while true; do
            if [ -f /data/job_completed ]; then
                echo "Job completed, performing final copy to S3..." &&
                rclone copy {exp_dir_q} {remote_q} --checksum --progress &&
                echo "Final copy completed, exiting..." &&
                break
            fi
            rclone copy {exp_dir_q} {remote_q} --ignore-checksum --retries 1 --quiet || echo "Copy attempt failed, retrying..."
            sleep 10
        done
    """

    job_manifest = {
        "apiVersion": "batch/v1",
        "kind": "Job",
        "metadata": {"name": name, "namespace": ns, "labels": {"app": name}},
        "spec": {
            "backoffLimit": 0,
            "ttlSecondsAfterFinished": 3600,  # 1 hour
            "template": {
                "metadata": {"labels": {"job": name}},
                "spec": {
                    "restartPolicy": "Never",
                    "securityContext": {"fsGroup": 1000},
                    "initContainers": [
                        {
                            "name": "s3-init",
                            "image": s3_sync_image,
                            "command": ["sh", "-c", s3_init_command],
                            "securityContext": {
                                "runAsUser": 1000,
                                "runAsGroup": 1000,
                                "runAsNonRoot": True,
                                "seccompProfile": {"type": "RuntimeDefault"},
                                "allowPrivilegeEscalation": False,
                                "capabilities": {"drop": ["ALL"]},
                            },
                            "env": rclone_env,
                            "volumeMounts": [{"name": "shared-data", "mountPath": "/data"}],
                        }
                    ],
                    "containers": [
                        {
                            "name": name,
                            "image": amber_image,
                            "workingDir": exp_dir,
                            "command": ["bash", "-c", amber_command],
                            "securityContext": {
                                "runAsUser": 1000,
                                "runAsGroup": 1000,
                                "runAsNonRoot": True,
                                "seccompProfile": {"type": "RuntimeDefault"},
                                "allowPrivilegeEscalation": False,
                                "capabilities": {"drop": ["ALL"]},
                            },
                            "env": [{"name": "OMP_NUM_THREADS", "value": str(ntomp)}],
                            "resources": {
                                "requests": {
                                    "cpu": str(np * ntomp) if binary == "pmemd.mpi" else str(ntomp),
                                    "memory": f"{4 * np}Gi" if binary == "pmemd.mpi" else "4Gi",
                                    GPU_TYPE: "1" if use_gpu else "0",
                                },
                                "limits": {
                                    "cpu": str(np * ntomp) if binary == "pmemd.mpi" else str(ntomp),
                                    "memory": f"{4 * np}Gi" if binary == "pmemd.mpi" else "4Gi",
                                    GPU_TYPE: "1" if use_gpu else "0",
                                },
                            },
                            "volumeMounts": [{"name": "shared-data", "mountPath": "/data"}],
                        },
                        {
                            "name": "s3-sync",
                            "image": s3_sync_image,
                            "command": ["sh", "-c", s3_sync_command],
                            "securityContext": {
                                "runAsUser": 1000,
                                "runAsGroup": 1000,
                                "runAsNonRoot": True,
                                "seccompProfile": {"type": "RuntimeDefault"},
                                "allowPrivilegeEscalation": False,
                                "capabilities": {"drop": ["ALL"]},
                            },
                            "env": rclone_env,
                            "resources": {
                                "requests": {"cpu": "100m", "memory": "128Mi"},
                                "limits": {"cpu": "200m", "memory": "256Mi"},
                            },
                            "volumeMounts": [{"name": "shared-data", "mountPath": "/data"}],
                        },
                    ],
                    "volumes": [
                        {
                            "name": "shared-data",
                            "emptyDir": {
                                "sizeLimit": "100Gi"
                            },
                        }
                    ],
                },
            },
        },
    }

    batch_v1.create_namespaced_job(namespace=ns, body=job_manifest)
    logger.info(f"Created AMBER job {name} in namespace {ns}")


def delete_job(ns: str, name: str) -> None:
    """
    Delete a Kubernetes job by name.

    Args:
        ns: Kubernetes namespace containing the job.
        name: Name of the job to delete.
    """
    if not ping_resource("job", name, ns):
        logger.warning(f"Job {name} does not exist in namespace {ns}. Skipping deletion.")
        return

    batch_v1.delete_namespaced_job(
        name=name,
        namespace=ns,
        body=client.V1DeleteOptions(
            propagation_policy="Background",
            grace_period_seconds=5,
        ),
    )
    logger.info(f"Deleted job {name} from namespace {ns}")


def ping_resource(resource_type: str, name: str, ns: str) -> bool:
    """
    Check if a Kubernetes resource exists.

    Args:
        resource_type: Type of resource ('svc', 'pod', 'configmap', 'secret', 'pvc', 'job').
        name: Name of the resource.
        ns: Kubernetes namespace to check.

    Returns:
        bool: True if the resource exists, False otherwise.

    Raises:
        ValueError: If an unsupported resource type is provided.
    """
    try:
        match resource_type:
            case "svc":
                core_v1.read_namespaced_service(name=name, namespace=ns)
            case "pod":
                core_v1.read_namespaced_pod(name=name, namespace=ns)
            case "configmap":
                core_v1.read_namespaced_config_map(name=name, namespace=ns)
            case "secret":
                core_v1.read_namespaced_secret(name=name, namespace=ns)
            case "pvc":
                core_v1.read_namespaced_persistent_volume_claim(name=name, namespace=ns)
            case "job":
                batch_v1.read_namespaced_job(name=name, namespace=ns)
            case _:
                raise ValueError(f"Unsupported resource type: {resource_type}")
        return True
    except ApiException:
        return False


def get_job_status(ns: str, name: str) -> JobStatus:
    """
    Get the current status of a Kubernetes job.

    Args:
        ns: Kubernetes namespace containing the job.
        name: Name of the job to check.

    Returns:
        JobStatus: Current status of the job (PENDING, RUNNING, TERMINATED, ERROR, or UNKNOWN).
    """
    try:
        job = cast("V1Job", batch_v1.read_namespaced_job(name=name, namespace=ns))

        if job.status and job.status.conditions:
            for condition in job.status.conditions:
                if condition.type == "Complete" and condition.status == "True":
                    return JobStatus.TERMINATED
                if condition.type == "Failed" and condition.status == "True":
                    return JobStatus.ERROR

        if job.status and job.status.succeeded and job.status.succeeded > 0:
            return JobStatus.TERMINATED
        if job.status and job.status.failed and job.status.failed > 0:
            return JobStatus.ERROR
        if job.status and job.status.active and job.status.active > 0:
            return JobStatus.RUNNING
        return JobStatus.PENDING

    except ApiException as e:
        if e.status == HTTPStatus.NOT_FOUND:
            return JobStatus.UNKNOWN
        return JobStatus.ERROR
