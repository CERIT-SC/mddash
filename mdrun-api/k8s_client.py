import logging
import os
import shlex
from http import HTTPStatus
from pathlib import Path
from typing import TYPE_CHECKING, Any, cast

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

_S3_SYNC_IMAGE = "rclone/rclone:1.74.4"
_SHARED_VOLUME_NAME = "shared-data"
_RUN_AS = {"runAsUser": 1000, "runAsGroup": 1000, "runAsNonRoot": True}
_SECURITY_CONTEXT = {
    **_RUN_AS,
    "seccompProfile": {"type": "RuntimeDefault"},
    "allowPrivilegeEscalation": False,
    "capabilities": {"drop": ["ALL"]},
}


def _q(value: str) -> str:
    return shlex.quote(value)


def _rclone_env() -> list[dict[str, str]]:
    return [
        {"name": "RCLONE_CONFIG_S3REMOTE_TYPE", "value": "s3"},
        {"name": "RCLONE_CONFIG_S3REMOTE_PROVIDER", "value": "Other"},
        {"name": "RCLONE_CONFIG_S3REMOTE_ACCESS_KEY_ID", "value": S3_ACCESS_KEY or ""},
        {"name": "RCLONE_CONFIG_S3REMOTE_SECRET_ACCESS_KEY", "value": S3_SECRET_KEY or ""},
        {"name": "RCLONE_CONFIG_S3REMOTE_ENDPOINT", "value": S3_ENDPOINT or ""},
    ]


def _s3_init_command(exp_dir: str, remote: str) -> str:
    return (
        f'echo "Downloading experiment data from object storage..." && '
        f"mkdir -p {_q(exp_dir)} && "
        f"rclone copy {_q(remote)} {_q(exp_dir + '/')} --progress || "
        f'echo "No existing data found, starting with empty directory"'
    )


def _s3_sync_command(local_dir: str, remote: str) -> str:
    return (
        f'echo "Starting continuous rclone copy process..." && '
        "while true; do\n"
        "    if [ -f /data/job_completed ]; then\n"
        '        echo "Job completed, performing final copy to S3..." &&\n'
        f"        rclone copy {_q(local_dir + '/')} {_q(remote)} --checksum --progress &&\n"
        '        echo "Final copy completed, exiting..." &&\n'
        "        break\n"
        "    fi\n"
        f"    rclone copy {_q(local_dir + '/')} {_q(remote)} --ignore-checksum --retries 1 --quiet || "
        'echo "Copy attempt failed, retrying..."\n'
        "    sleep 10\n"
        "done\n"
    )


def _volume_mount(path: str = "/data") -> dict[str, str]:
    return {"name": _SHARED_VOLUME_NAME, "mountPath": path}


def _sim_sync_remote(bucket_name: str, experiment_id: str, primary_file: str) -> str:
    sim_rel = Path(primary_file).parent.as_posix()
    base = f"s3remote:{bucket_name}/{experiment_id}/"
    return f"{base}{sim_rel}/" if sim_rel != "." else base


def _build_job_manifest(
    *,
    name: str,
    ns: str,
    exp_dir: str,
    remote: str,
    working_dir: str,
    sync_remote: str,
    sim_image: str,
    sim_command: str,
    sim_resources: dict[str, Any],
    sim_env: list[dict[str, str]] | None = None,
) -> dict[str, Any]:
    s3_init = _s3_init_command(exp_dir, remote)
    s3_sync = _s3_sync_command(working_dir, sync_remote)
    vol_mount = _volume_mount()
    rclone_env = _rclone_env()

    return {
        "apiVersion": "batch/v1",
        "kind": "Job",
        "metadata": {"name": name, "namespace": ns, "labels": {"app": name}},
        "spec": {
            "backoffLimit": 0,
            "ttlSecondsAfterFinished": 3600,
            "template": {
                "metadata": {"labels": {"job": name}},
                "spec": {
                    "restartPolicy": "Never",
                    "securityContext": {"fsGroup": 1000},
                    "initContainers": [
                        {
                            "name": "s3-init",
                            "image": _S3_SYNC_IMAGE,
                            "command": ["sh", "-c", s3_init],
                            "securityContext": _SECURITY_CONTEXT,
                            "env": rclone_env,
                            "volumeMounts": [vol_mount],
                        }
                    ],
                    "containers": [
                        {
                            "name": name,
                            "image": sim_image,
                            "imagePullPolicy": "Always",
                            "workingDir": working_dir,
                            "command": ["bash", "-c", sim_command],
                            "securityContext": _SECURITY_CONTEXT,
                            "env": sim_env or [],
                            "resources": sim_resources,
                            "volumeMounts": [vol_mount],
                        },
                        {
                            "name": "s3-sync",
                            "image": _S3_SYNC_IMAGE,
                            "command": ["sh", "-c", s3_sync],
                            "securityContext": _SECURITY_CONTEXT,
                            "env": rclone_env,
                            "resources": {
                                "requests": {"cpu": "100m", "memory": "128Mi"},
                                "limits": {"cpu": "200m", "memory": "256Mi"},
                            },
                            "volumeMounts": [vol_mount],
                        },
                    ],
                    "volumes": [
                        {
                            "name": _SHARED_VOLUME_NAME,
                            "emptyDir": {"sizeLimit": "100Gi"},
                        }
                    ],
                },
            },
        },
    }


def _gmx_resources(np: int, ntomp: int, nb: str, pme: str) -> dict[str, Any]:
    use_gpu = nb == "gpu" or pme == "gpu"
    return {
        "requests": {
            "cpu": str(np * ntomp),
            "memory": f"{4 * np}Gi",
            GPU_TYPE: "1" if use_gpu else "0",
        },
        "limits": {
            "cpu": str(np * ntomp),
            "memory": f"{4 * np}Gi",
            GPU_TYPE: "1" if use_gpu else "0",
        },
    }


def _mdin_patch_command(mdin_name: str, ewald: str) -> str:
    """
    Build an awk command that patches the &ewald namelist in the mdin file.

    Returns:
        Awk command string.
    """
    match ewald:
        case "optimized":
            netfrc, skin_permit = "0", "0.75"
        case _:
            netfrc, skin_permit = "1", "1.0"

    return (
        f"awk '\n"
        "BEGIN { skip=0 }\n"
        '{ orig=$0; $0=tolower($0); gsub(/^[[:space:]]+/, "", $0); gsub(/[[:space:]]+$/, "", $0) }\n'
        "$0 ~ /^&ewald/ { skip=1; next }\n"
        'skip && ($0 == "/" || $0 == "&end") { skip=0; next }\n'
        "{ if (!skip) print orig }\n"
        "END {\n"
        '    print ""; print "&ewald";\n'
        f'    print "  netfrc = {netfrc},";\n'
        f'    print "  skin_permit = {skin_permit},";\n'
        '    print " /"\n'
        f"}}' < {_q(mdin_name)} > {_q(mdin_name)}.tmp && mv {_q(mdin_name)}.tmp {_q(mdin_name)}"
    )


def _amber_command(
    binary: str, np: int, ewald: str, extra_args: str, base_flags: str, mdin_name: str, name: str
) -> tuple[str, bool]:
    extra_part = f" {extra_args}" if extra_args else ""
    patch_step = _mdin_patch_command(mdin_name, ewald)
    tee_redirect = f" > >(tee {_q(f'{name}.out')}) 2> >(tee {_q(f'{name}.err')} >&2)"

    if binary == "pmemd.cuda":
        command = "\n".join([
            "set -euo pipefail",
            "trap 'touch /data/job_completed' EXIT TERM INT",
            patch_step,
            " ".join(["pmemd.cuda", base_flags]).rstrip() + extra_part + tee_redirect,
        ])
        return command, True

    command = "\n".join([
        "set -euo pipefail",
        "trap 'touch /data/job_completed' EXIT TERM INT",
        patch_step,
        " ".join(["mpirun", "-np", str(np), "pmemd.MPI", base_flags]) + extra_part + tee_redirect,
    ])
    return command, False


def _amber_resources(binary: str, np: int, ntomp: int, use_gpu: bool) -> dict[str, Any]:
    cpu = str(np * ntomp) if binary == "pmemd.mpi" else str(ntomp)
    memory = f"{4 * np}Gi" if binary == "pmemd.mpi" else "4Gi"
    return {
        "requests": {"cpu": cpu, "memory": memory, GPU_TYPE: "1" if use_gpu else "0"},
        "limits": {"cpu": cpu, "memory": memory, GPU_TYPE: "1" if use_gpu else "0"},
    }


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
    """Create a GROMACS MD simulation job in Kubernetes."""
    if ping_resource("job", name, ns):
        logger.warning(f"Job {name} already exists in namespace {ns}. Skipping creation.")
        return

    np = int(np)
    ntomp = int(ntomp)
    nb = nb.lower()
    pme = pme.lower()

    exp_dir = f"/data/{experiment_id}"
    remote = f"s3remote:{bucket_name}/{experiment_id}/"
    extra_part = f" {extra_args}" if extra_args else ""

    working_dir = str(Path(exp_dir) / Path(deffnm).parent)
    sync_remote = _sim_sync_remote(bucket_name, experiment_id, deffnm)
    deffnm_arg = Path(deffnm).name

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
                _q(deffnm_arg),
            ])
            + extra_part
            + f" > >(tee {_q(f'{name}.out')}) 2> >(tee {_q(f'{name}.err')} >&2)"
        ),
        "echo 'Simulation completed.'",
    ])

    manifest = _build_job_manifest(
        name=name,
        ns=ns,
        exp_dir=exp_dir,
        remote=remote,
        working_dir=working_dir,
        sync_remote=sync_remote,
        sim_image=GMX_IMAGE,
        sim_command=gromacs_command,
        sim_resources=_gmx_resources(np, ntomp, nb, pme),
        sim_env=[
            {"name": "OMP_NUM_THREADS", "value": str(ntomp)},
            {"name": "TZ", "value": "UTC"},
        ],
    )

    batch_v1.create_namespaced_job(namespace=ns, body=manifest)
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
    """Create an AMBER MD simulation job in Kubernetes."""
    if ping_resource("job", name, ns):
        logger.warning(f"Job {name} already exists in namespace {ns}. Skipping creation.")
        return

    np = int(np)
    ntomp = int(ntomp)
    binary = binary.lower()
    ewald = ewald.lower()

    exp_dir = f"/data/{experiment_id}"
    remote = f"s3remote:{bucket_name}/{experiment_id}/"

    sim_rel = Path(mdin_name).parent.as_posix()
    mdin_rel = Path(mdin_name).name
    prmtop_rel = os.path.relpath(prmtop_name, start=sim_rel)
    inpcrd_rel = os.path.relpath(inpcrd_name, start=sim_rel)
    output_prefix = Path(mdin_name).stem

    base_flags = (
        f"-O -i {_q(mdin_rel)} -o {_q(f'{output_prefix}.out')} "
        f"-p {_q(prmtop_rel)} -c {_q(inpcrd_rel)} "
        f"-r {_q(f'{output_prefix}.rst7')} -x {_q(f'{output_prefix}.nc')} "
        f"-inf {_q(f'{output_prefix}.mdinfo')}"
    )

    amber_command, use_gpu = _amber_command(binary, np, ewald, extra_args, base_flags, mdin_rel, name)

    manifest = _build_job_manifest(
        name=name,
        ns=ns,
        exp_dir=exp_dir,
        remote=remote,
        working_dir=str(Path(exp_dir) / Path(mdin_name).parent),
        sync_remote=_sim_sync_remote(bucket_name, experiment_id, mdin_name),
        sim_image=AMBER_IMAGE,
        sim_command=amber_command,
        sim_resources=_amber_resources(binary, np, ntomp, use_gpu),
        sim_env=[
            {"name": "OMP_NUM_THREADS", "value": str(ntomp)},
            {"name": "TZ", "value": "UTC"},
        ],
    )

    batch_v1.create_namespaced_job(namespace=ns, body=manifest)
    logger.info(f"Created AMBER job {name} in namespace {ns}")


def delete_job(ns: str, name: str) -> None:
    """Delete a Kubernetes job by name."""
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
        True if the resource exists, False otherwise.

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
        Current status of the job (PENDING, RUNNING, TERMINATED, ERROR, or UNKNOWN).
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
            # active > 0 means K8s created a pod, but it may still be pulling image or scheduling.
            # Check pod phase to distinguish PENDING (unscheduled/image-pull) from actual RUNNING.
            try:
                pods = core_v1.list_namespaced_pod(namespace=ns, label_selector=f"job-name={name}", limit=1)
                if pods.items:
                    phase = pods.items[0].status.phase
                    if phase == "Running":
                        return JobStatus.RUNNING
                    # Pod exists but not running yet (Pending, ContainerCreating, etc.)
                    return JobStatus.PENDING
            except ApiException:
                pass
            # Can't determine pod phase — fall back to RUNNING since job is active
            return JobStatus.RUNNING
        return JobStatus.PENDING

    except ApiException as e:
        if e.status == HTTPStatus.NOT_FOUND:
            return JobStatus.UNKNOWN
        return JobStatus.ERROR
