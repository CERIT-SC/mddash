import logging
import math
import os
import re
import shlex
from dataclasses import dataclass
from datetime import UTC, datetime
from http import HTTPStatus
from pathlib import Path
from typing import TYPE_CHECKING, Any, cast

from config import AMBER_IMAGE, GMX_IMAGE, GPU_PRODUCT, GPU_TYPE, S3_ACCESS_KEY, S3_ENDPOINT, S3_SECRET_KEY
from enums import JobStatus
from kubernetes import client, config
from kubernetes.client.rest import ApiException
from urllib3.exceptions import HTTPError

if TYPE_CHECKING:
    from kubernetes.client import V1Job, V1Pod


logger = logging.getLogger(__name__)

config.load_incluster_config()
core_v1 = client.CoreV1Api()
batch_v1 = client.BatchV1Api()

_S3_SYNC_IMAGE = "rclone/rclone:1.74.4"
_SHARED_VOLUME_NAME = "shared-data"
# Grace period for stop deletions: mdrun needs time to write its final checkpoint
# and the s3-sync sidecar to upload it before the pod is torn down.
STOP_GRACE_PERIOD_SECONDS = 60
_RUN_AS = {"runAsUser": 1000, "runAsGroup": 1000, "runAsNonRoot": True}
_SECURITY_CONTEXT = {
    **_RUN_AS,
    "seccompProfile": {"type": "RuntimeDefault"},
    "allowPrivilegeEscalation": False,
    "capabilities": {"drop": ["ALL"]},
}
# With backoffLimit 0 a terminal pod phase (Succeeded/Failed) is the final outcome
# even before the job controller stamps the Job object; other phases are pre-start.
_POD_PHASE_STATUS = {
    "Running": JobStatus.RUNNING,
    "Succeeded": JobStatus.FINISHED,
    "Failed": JobStatus.ERROR,
}
# A stop deletes the pod before its exit line, so the stored measurement can trail by one interval.
USAGE_INTERVAL_SECONDS = 60
_USAGE_PREFIX = "mddash-usage "
# Enough to reach back one interval past chatty simulation output.
_USAGE_LOG_TAIL_LINES = 2000
# Stop, DELETE, and status reads wait on the log read. urllib3 retries a timeout three times, so they
# wait up to four times this, which must stay within the dashboard's 10 s for a stop.
_USAGE_LOG_TIMEOUT_SECONDS = 2
# Largest accepted field values: SQLite's INTEGER limit, and datetime's last second for timestamps.
_MAX_USAGE_VALUE = 2**63 - 1
_MAX_USAGE_EPOCH = 253_402_300_799
_USAGE_TIMESTAMPS = frozenset({"started", "at"})


@dataclass(frozen=True)
class JobResources:
    """What a simulation container reserves; requests equal limits."""

    cpu: int
    memory_gib: int
    gpus: int

    def to_k8s(self) -> dict[str, Any]:
        """Kubernetes requests and limits for the simulation container."""
        quantities = {"cpu": str(self.cpu), "memory": f"{self.memory_gib}Gi", GPU_TYPE: str(self.gpus)}
        return {"requests": quantities, "limits": dict(quantities)}


@dataclass(frozen=True)
class MeasuredUsage:
    """What a simulation container measured of itself, by its own clock; None where it could not."""

    cpu_core_seconds: float | None
    memory_peak_gib: float | None
    gpu_utilization: float | None
    gpu_memory_peak_gib: float | None
    complete: bool
    container_started_at: datetime | None = None
    measured_at: datetime | None = None
    cpu_throttled_seconds: float | None = None
    cpu_stall_seconds: float | None = None
    memory_stall_seconds: float | None = None
    io_stall_seconds: float | None = None
    oom_kills: int | None = None
    io_read_bytes: int | None = None
    io_write_bytes: int | None = None
    gpu_power_watts: float | None = None
    ns_per_day: float | None = None


def gmx_resources(np: int, ntomp: int, nb: str, pme: str) -> JobResources:
    """Size a GROMACS run: a core per OpenMP thread of each rank, 4 GiB per rank, a GPU when any work is offloaded."""
    use_gpu = "gpu" in {nb.lower(), pme.lower()}
    return JobResources(cpu=np * ntomp, memory_gib=4 * np, gpus=1 if use_gpu else 0)


def amber_resources(binary: str, np: int, ntomp: int) -> JobResources:
    """Size an AMBER run: MPI ranks for pmemd.MPI, one process with a GPU for pmemd.cuda."""
    binary = binary.lower()
    if binary == "pmemd.mpi":
        return JobResources(cpu=np * ntomp, memory_gib=4 * np, gpus=0)
    return JobResources(cpu=ntomp, memory_gib=4, gpus=1 if binary == "pmemd.cuda" else 0)


def _owner_metadata(
    engine: str, owner: str | None, owner_namespace: str | None
) -> tuple[dict[str, str], dict[str, str]]:
    """Labels and annotations attributing a job to its user; usernames are not always valid label values."""
    labels = {"mddash.io/workload": "mdrun", "mddash.io/engine": engine}
    if owner_namespace:
        labels["mddash.io/user-namespace"] = owner_namespace
    annotations = {"mddash.io/user": owner} if owner else {}
    return labels, annotations


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
    # On pod deletion the sidecar gets TERM immediately; without the trap it would die
    # before the final copy, losing the last checkpoint. Trap waits (bounded) for the
    # sim's completion marker, then uploads.
    return (
        "final_copy() {\n"
        '    echo "Performing final copy to S3..." &&\n'
        f"    rclone copy {_q(local_dir + '/')} {_q(remote)} --checksum --progress &&\n"
        '    echo "Final copy completed."\n'
        "}\n"
        "on_term() {\n"
        '    echo "Termination requested, waiting for simulation to finish..."\n'
        "    i=0\n"
        '    while [ ! -f /data/job_completed ] && [ "$i" -lt 30 ]; do\n'
        "        sleep 5\n"
        "        i=$((i + 5))\n"
        "    done\n"
        "    final_copy\n"
        "    exit 0\n"
        "}\n"
        "trap on_term TERM INT\n"
        'echo "Starting continuous rclone copy process..."\n'
        "while true; do\n"
        "    if [ -f /data/job_completed ]; then\n"
        "        final_copy\n"
        "        break\n"
        "    fi\n"
        f"    rclone copy {_q(local_dir + '/')} {_q(remote)} --ignore-checksum --retries 1 --quiet || "
        'echo "Copy attempt failed, retrying..."\n'
        "    sleep 10\n"
        "done\n"
    )


# awk programs printing ``mddash-usage`` fields from cgroup v2 files; stalls are pressure-stall "some" totals.
_CGROUP_FIELDS = {
    "cpu.stat": '$1 == "usage_usec" {printf " cpu_usec=%s", $2} '
    '$1 == "throttled_usec" {printf " cpu_throttled_usec=%s", $2}',
    "memory.peak": 'NR == 1 {printf " memory_peak_bytes=%s", $1}',
    "memory.events": '$1 == "oom_kill" {printf " oom_kills=%s", $2}',
    **{
        f"{resource}.pressure": f'$1 == "some" {{for (i = 2; i <= NF; i++) '
        f'if ($i ~ /^total=/) printf " {resource}_stall_usec=%s", substr($i, 7)}}'
        for resource in ("cpu", "memory", "io")
    },
}
_IO_STAT_FIELDS = (
    '{for (i = 2; i <= NF; i++) {split($i, kv, "="); if (kv[1] == "rbytes") r += kv[2]; '
    'else if (kv[1] == "wbytes") w += kv[2]}} END {printf " io_read_bytes=%.0f io_write_bytes=%.0f", r, w}'
)
_GPU_FIELDS = (
    "{n++; u += $1; if ($2 > m) m = $2; if ($3 ~ /^[0-9.]+$/) {p += $3; pn++}} "
    'END {printf " gpu_samples=%d gpu_util_sum=%d gpu_memory_peak_mib=%d", n, u, m; '
    'if (pn) printf " gpu_power_sum_w=%.1f gpu_power_samples=%d", p, pn}'
)


def _gromacs_performance(log_name: str) -> str:
    """Command printing the ns/day of mdrun's last end-of-run report; ``-cpi`` runs append theirs to the same log."""
    return f'awk \'$1 == "Performance:" {{v = $2}} END {{if (v != "") printf " ns_per_day=%s", v}}\' {_q(log_name)}'


def _amber_performance(mdout_name: str) -> str:
    """Command printing pmemd's ns/day over all steps, the last figure in its timing summary."""
    return (
        'awk \'{for (i = 1; i < NF - 1; i++) if ($i == "ns/day" && $(i + 1) == "=") v = $(i + 2)} '
        f'END {{if (v != "") printf " ns_per_day=%s", v}}\' {_q(mdout_name)}'
    )


def _usage_block(
    gpus: bool, interval: float = USAGE_INTERVAL_SECONDS, cgroup: str = "/sys/fs/cgroup", performance: str = ""
) -> str:
    """
    Log the container's own counters as ``mddash-usage`` lines; every command tolerates failure.

    Only GPU jobs run ``nvidia-smi``: a CPU job on a GPU node may see other jobs' GPUs.
    """
    lines = [
        "MDDASH_STARTED=$(date +%s 2>/dev/null) || MDDASH_STARTED=''",
        "MDDASH_GPU_LOG=$(mktemp 2>/dev/null) || MDDASH_GPU_LOG=" if gpus else "MDDASH_GPU_LOG=",
    ]
    if gpus:
        lines += [
            "mddash_gpu_sample() {",
            "    timeout 10 nvidia-smi --query-gpu=utilization.gpu,memory.used,power.draw --format=csv,noheader,nounits"
            ' >> "$MDDASH_GPU_LOG" 2>/dev/null || true',
            "}",
        ]
    io_stat = _q(f"{cgroup}/io.stat")
    lines += [
        # Runs only inside $(...), where bash drops errexit, so an unreadable counter just prints nothing.
        "mddash_counters() {",
        *(f"    awk '{program}' {_q(f'{cgroup}/{name}')} 2>/dev/null" for name, program in _CGROUP_FIELDS.items()),
        f"    if [ -r {io_stat} ]; then awk '{_IO_STAT_FIELDS}' {io_stat} 2>/dev/null; fi",
        f"    if [ -s \"$MDDASH_GPU_LOG\" ]; then awk -F', *' '{_GPU_FIELDS}' \"$MDDASH_GPU_LOG\" 2>/dev/null; fi",
        "    return 0",
        "}",
        "mddash_usage() {",
        "    local fields",
        "    fields=$(mddash_counters) || fields=''",
        f'    echo "{_USAGE_PREFIX}final=$1 started=$MDDASH_STARTED at=$(date +%s 2>/dev/null)$fields${{2:-}}"',
        "}",
        f"while sleep {interval} >/dev/null 2>&1; do",
        *(["    mddash_gpu_sample"] if gpus else []),
        "    mddash_usage 0",
        "done &",
        "MDDASH_SAMPLER=$!",
        "mddash_usage_final() {",
        # A failed run never reached its own report, and its log may hold an earlier run's.
        "    local failed=$?",
        # The sampler's sleep would outlive it.
        '    pkill -P "$MDDASH_SAMPLER" 2>/dev/null || true',
        '    kill "$MDDASH_SAMPLER" 2>/dev/null || true',
        f'    mddash_usage 1 "$([ "$failed" -ne 0 ] || {performance} 2>/dev/null || true)"'
        if performance
        else "    mddash_usage 1",
        "}",
    ]
    return "\n".join(lines)


def _sim_guard_block(sim_process: str) -> str:
    """
    Guard for the backgrounded sim.

    TERM goes to the sim process by name (an MPI launcher kills ranks on TERM
    before mdrun checkpoints); $MD_PID is the fallback. Marker on every exit
    path triggers the s3-sync sidecar's final copy.
    """
    return "\n".join([
        "MD_PID=$!",
        "on_term() {",
        '    echo "Termination requested, signaling simulation to checkpoint..."',
        f"    pkill -TERM -x '{re.escape(sim_process)}' 2>/dev/null || kill -TERM \"$MD_PID\" 2>/dev/null || true",
        '    wait "$MD_PID" || true',
        "    exit 0",
        "}",
        "trap on_term TERM INT",
        # Under set -e a failing trap command skips the rest, and s3-sync would wait for the marker in vain.
        "trap 'mddash_usage_final || true; touch /data/job_completed' EXIT",
        'wait "$MD_PID"',
        "echo 'Simulation completed.'",
    ])


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
    use_gpu: bool,
    engine: str,
    owner: str | None,
    owner_namespace: str | None,
    sim_env: list[dict[str, str]] | None = None,
) -> dict[str, Any]:
    s3_init = _s3_init_command(exp_dir, remote)
    s3_sync = _s3_sync_command(working_dir, sync_remote)
    vol_mount = _volume_mount()
    rclone_env = _rclone_env()
    labels, annotations = _owner_metadata(engine, owner, owner_namespace)
    annotations_field = {"annotations": annotations} if annotations else {}

    return {
        "apiVersion": "batch/v1",
        "kind": "Job",
        "metadata": {"name": name, "namespace": ns, "labels": {"app": name, **labels}, **annotations_field},
        "spec": {
            "backoffLimit": 0,
            "ttlSecondsAfterFinished": 3600,
            "template": {
                "metadata": {"labels": {"job": name, **labels}, **annotations_field},
                "spec": {
                    "restartPolicy": "Never",
                    "securityContext": {"fsGroup": 1000},
                    **({"nodeSelector": {"nvidia.com/gpu.product": GPU_PRODUCT}} if use_gpu and GPU_PRODUCT else {}),
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
    binary: str, np: int, ewald: str, extra_args: str, base_flags: str, mdin_name: str, name: str, mdout_name: str
) -> tuple[str, bool]:
    extra_part = f" {extra_args}" if extra_args else ""
    performance = _amber_performance(mdout_name)
    patch_step = _mdin_patch_command(mdin_name, ewald)
    tee_redirect = f" > >(tee {_q(f'{name}.out')}) 2> >(tee {_q(f'{name}.err')} >&2)"

    if binary == "pmemd.cuda":
        command = "\n".join([
            "set -euo pipefail",
            patch_step,
            _usage_block(gpus=True, performance=performance),
            " ".join(["pmemd.cuda", base_flags]).rstrip() + extra_part + tee_redirect + " &",
            _sim_guard_block("pmemd.cuda"),
        ])
        return command, True

    command = "\n".join([
        "set -euo pipefail",
        patch_step,
        _usage_block(gpus=False, performance=performance),
        " ".join(["mpirun", "-np", str(np), "pmemd.MPI", base_flags]) + extra_part + tee_redirect + " &",
        _sim_guard_block("pmemd.MPI"),
    ])
    return command, False


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
    owner: str | None = None,
    owner_namespace: str | None = None,
) -> None:
    """Create a GROMACS MD simulation job in Kubernetes."""
    if ping_resource("job", name, ns):
        logger.warning(f"Job {name} already exists in namespace {ns}. Skipping creation.")
        return

    np = int(np)
    ntomp = int(ntomp)
    nb = nb.lower()
    pme = pme.lower()
    use_gpu = nb == "gpu" or pme == "gpu"

    exp_dir = f"/data/{experiment_id}"
    remote = f"s3remote:{bucket_name}/{experiment_id}/"
    extra_part = f" {extra_args}" if extra_args else ""

    working_dir = str(Path(exp_dir) / Path(deffnm).parent)
    sync_remote = _sim_sync_remote(bucket_name, experiment_id, deffnm)
    deffnm_arg = Path(deffnm).name

    gromacs_command = "\n".join([
        "set -euo pipefail",
        _usage_block(gpus=use_gpu, performance=_gromacs_performance(f"{deffnm_arg}.log")),
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
            + f" > >(tee {_q(f'{name}.out')}) 2> >(tee {_q(f'{name}.err')} >&2) &"
        ),
        _sim_guard_block("gmx"),
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
        sim_resources=gmx_resources(np, ntomp, nb, pme).to_k8s(),
        use_gpu=use_gpu,
        engine="gmx",
        owner=owner,
        owner_namespace=owner_namespace,
        sim_env=[
            {"name": "OMP_NUM_THREADS", "value": str(ntomp)},
            {"name": "TZ", "value": "UTC"},
        ],
    )

    batch_v1.create_namespaced_job(namespace=ns, body=manifest)
    logger.info(f"Created GROMACS job {name} in namespace {ns}")


def _amber_restart_prefix(mdin_name: str, inpcrd_name: str, output_prefix: str) -> str:
    """-r <stem>.rst7 would clobber a colliding coordinates input (md.mdin + md.rst7)."""
    if Path(inpcrd_name) == Path(mdin_name).parent / f"{output_prefix}.rst7":
        return _q(f"{output_prefix}_out.rst7")
    return _q(f"{output_prefix}.rst7")


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
    owner: str | None = None,
    owner_namespace: str | None = None,
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
        f"-r {_amber_restart_prefix(mdin_name, inpcrd_name, output_prefix)} "
        f"-x {_q(f'{output_prefix}.nc')} -inf {_q(f'{output_prefix}.mdinfo')}"
    )

    amber_command, use_gpu = _amber_command(
        binary, np, ewald, extra_args, base_flags, mdin_rel, name, f"{output_prefix}.out"
    )

    manifest = _build_job_manifest(
        name=name,
        ns=ns,
        exp_dir=exp_dir,
        remote=remote,
        working_dir=str(Path(exp_dir) / Path(mdin_name).parent),
        sync_remote=_sim_sync_remote(bucket_name, experiment_id, mdin_name),
        sim_image=AMBER_IMAGE,
        sim_command=amber_command,
        sim_resources=amber_resources(binary, np, ntomp).to_k8s(),
        use_gpu=use_gpu,
        engine="amber",
        owner=owner,
        owner_namespace=owner_namespace,
        sim_env=[
            {"name": "OMP_NUM_THREADS", "value": str(ntomp)},
            {"name": "TZ", "value": "UTC"},
        ],
    )

    batch_v1.create_namespaced_job(namespace=ns, body=manifest)
    logger.info(f"Created AMBER job {name} in namespace {ns}")


def delete_job(ns: str, name: str, grace_period_seconds: int = 5) -> None:
    """
    Delete a Kubernetes job by name; a missing job is a no-op.

    Raises:
        ApiException: Any other API error. The job may still run, so callers must not record it gone.
    """
    try:
        batch_v1.delete_namespaced_job(
            name=name,
            namespace=ns,
            body=client.V1DeleteOptions(
                propagation_policy="Background",
                grace_period_seconds=grace_period_seconds,
            ),
        )
    except ApiException as e:
        if e.status != HTTPStatus.NOT_FOUND:
            raise
        logger.warning(f"Job {name} does not exist in namespace {ns}. Skipping deletion.")
        return
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


def get_job_pod(ns: str, name: str) -> "V1Pod | None":
    """Find the job's pod; None without a readable one."""
    try:
        pods = core_v1.list_namespaced_pod(namespace=ns, label_selector=f"job-name={name}", limit=1)
    except ApiException:
        return None
    return pods.items[0] if pods.items else None


def get_pod_times(pod: "V1Pod | None") -> tuple[datetime | None, datetime | None]:
    """
    Allocation window of a job's pod: kubelet acceptance until its last container exits.

    Returns:
        ``(start, end)``; ``end`` is None while any container runs, both are None without a pod.
    """
    if pod is None:
        return None, None

    status = pod.status
    containers = status.container_statuses or []
    exits = [c.state.terminated.finished_at for c in containers if c.state and c.state.terminated]
    if containers and len(exits) == len(containers) and all(exits):
        return status.start_time, max(exits)
    return status.start_time, None


def _numbers(line: str, job: str) -> dict[str, float]:
    """Keep a usage line's fields that hold a number in range; warn about the rest, which only a bug or forgery writes."""
    numbers: dict[str, float] = {}
    rejected = []
    for field in line[len(_USAGE_PREFIX) :].split():
        key, _, text = field.partition("=")
        try:
            value = float(text)
        except ValueError:
            value = math.nan
        if 0 <= value <= (_MAX_USAGE_EPOCH if key in _USAGE_TIMESTAMPS else _MAX_USAGE_VALUE):
            numbers[key] = value
        elif text:  # empty: the container could not measure it
            rejected.append(field)
    if rejected:
        logger.warning("Ignoring malformed usage fields of %s: %s", job, " ".join(rejected))
    return numbers


def _count(numbers: dict[str, float], key: str) -> int | None:
    value = numbers.get(key)
    return None if value is None else int(value)


def _seconds(numbers: dict[str, float], key: str) -> float | None:
    """Seconds from a microsecond counter."""
    usec = numbers.get(key)
    return None if usec is None else usec / 1_000_000


def _timestamp(numbers: dict[str, float], key: str) -> datetime | None:
    epoch = numbers.get(key)
    return None if epoch is None else datetime.fromtimestamp(epoch, UTC)


def _ratio(numerator: float | None, denominator: float | None) -> float | None:
    return numerator / denominator if numerator is not None and denominator else None


def parse_usage_line(line: str, job: str) -> MeasuredUsage | None:
    """Read one ``mddash-usage`` line of ``job``'s log; None when it is not one or measured nothing."""
    if not line.startswith(_USAGE_PREFIX):
        return None
    numbers = _numbers(line, job)
    memory_bytes = numbers.get("memory_peak_bytes")
    gpu_samples = numbers.get("gpu_samples")
    gpu_util_sum = numbers.get("gpu_util_sum")
    gpu_memory_mib = numbers.get("gpu_memory_peak_mib")
    gpu = bool(gpu_samples) and gpu_util_sum is not None
    if "cpu_usec" not in numbers and memory_bytes is None and not gpu:
        return None
    return MeasuredUsage(
        cpu_core_seconds=_seconds(numbers, "cpu_usec"),
        memory_peak_gib=None if memory_bytes is None else memory_bytes / 2**30,
        gpu_utilization=_ratio(gpu_util_sum, gpu_samples) if gpu else None,
        gpu_memory_peak_gib=gpu_memory_mib / 1024 if gpu and gpu_memory_mib is not None else None,
        complete=numbers.get("final") == 1,
        container_started_at=_timestamp(numbers, "started"),
        measured_at=_timestamp(numbers, "at"),
        cpu_throttled_seconds=_seconds(numbers, "cpu_throttled_usec"),
        cpu_stall_seconds=_seconds(numbers, "cpu_stall_usec"),
        memory_stall_seconds=_seconds(numbers, "memory_stall_usec"),
        io_stall_seconds=_seconds(numbers, "io_stall_usec"),
        oom_kills=_count(numbers, "oom_kills"),
        io_read_bytes=_count(numbers, "io_read_bytes"),
        io_write_bytes=_count(numbers, "io_write_bytes"),
        gpu_power_watts=_ratio(numbers.get("gpu_power_sum_w"), numbers.get("gpu_power_samples")) if gpu else None,
        ns_per_day=numbers.get("ns_per_day"),
    )


def get_measured_usage(ns: str, name: str, pod: "V1Pod | None") -> MeasuredUsage | None:
    """Latest measurement the job's simulation container logged; None on any read failure, never an error."""
    if pod is None:
        return None
    try:
        # Raw bytes: kubernetes 36 returns a preloaded text/plain body as the repr of its bytes.
        response = core_v1.read_namespaced_pod_log(
            name=pod.metadata.name,
            namespace=ns,
            container=name,
            tail_lines=_USAGE_LOG_TAIL_LINES,
            _preload_content=False,
            _request_timeout=_USAGE_LOG_TIMEOUT_SECONDS,
        )
        try:
            log = (response.data or b"").decode("utf-8", errors="replace")
        finally:
            response.release_conn()
    except (ApiException, HTTPError):
        return None
    # The kubelet joins a line onto unterminated output before it, such as `mdrun -v` progress.
    latest = next((line for line in reversed(log.splitlines()) if _USAGE_PREFIX in line), None)
    return None if latest is None else parse_usage_line(latest[latest.rindex(_USAGE_PREFIX) :], name)


def get_job_status(ns: str, name: str) -> JobStatus:
    """
    Get the current status of a Kubernetes job.

    Args:
        ns: Kubernetes namespace containing the job.
        name: Name of the job to check.

    Returns:
        Current status of the job (PENDING, RUNNING, FINISHED, ERROR, or UNKNOWN when the job is gone).

    Raises:
        ApiException: The job could not be read. That says nothing about the job, so it is never a status.
    """
    try:
        job = cast("V1Job", batch_v1.read_namespaced_job(name=name, namespace=ns))

        if job.status and job.status.conditions:
            for condition in job.status.conditions:
                if condition.type == "Complete" and condition.status == "True":
                    return JobStatus.FINISHED
                if condition.type == "Failed" and condition.status == "True":
                    return JobStatus.ERROR

        if job.status and job.status.succeeded and job.status.succeeded > 0:
            return JobStatus.FINISHED
        if job.status and job.status.failed and job.status.failed > 0:
            return JobStatus.ERROR
        if job.status and job.status.active and job.status.active > 0:
            # active > 0 means K8s created a pod, but it may still be pulling image or scheduling.
            # Check pod phase to distinguish PENDING (unscheduled/image-pull) from actual RUNNING.
            try:
                pods = core_v1.list_namespaced_pod(namespace=ns, label_selector=f"job-name={name}", limit=1)
                if pods.items:
                    return _POD_PHASE_STATUS.get(pods.items[0].status.phase, JobStatus.PENDING)
            except ApiException:
                pass
            # Pod phase is unknown, so fall back to RUNNING since the job is active.
            return JobStatus.RUNNING
        return JobStatus.PENDING

    except ApiException as e:
        if e.status == HTTPStatus.NOT_FOUND:
            return JobStatus.UNKNOWN
        raise
