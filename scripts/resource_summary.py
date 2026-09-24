#!/usr/bin/env python3
"""
Offline resource budget calculator for mddash namespaces.

Reads resource configuration from config YAML files and computes the
recommended namespace quota values for both the hub namespace and
per-user namespaces.

Usage:
    python3 scripts/resource_summary.py <config.yaml>          # human-readable table
    python3 scripts/resource_summary.py --json <config.yaml>   # hub totals as JSON (for install.sh)

Example:
    make resources ENV=dev
    python3 scripts/resource_summary.py config.dev.yaml
"""

import json
import subprocess
import sys
from collections.abc import Iterable
from typing import NamedTuple


class Row(NamedTuple):
    """One container's resource footprint. CPU in millicores, memory in bytes."""

    name: str
    cpu_req: int
    mem_req: int
    cpu_lim: int
    mem_lim: int


def row_mib(name: str, cpu_req: int, mem_req: int, cpu_lim: int, mem_lim: int) -> Row:
    """Build a Row from values written in millicores/MiB (as the constants below are)."""
    return Row(name, cpu_req, mem_req * 1024**2, cpu_lim, mem_lim * 1024**2)


def row_cfg(name: str, config: str, prefix: str) -> Row:
    """Build a Row from a config section shaped as {requests, limits}.{cpu, memory}."""
    return Row(
        name,
        parse_cpu(yq(f"{prefix}.requests.cpu", config)),
        parse_memory(yq(f"{prefix}.requests.memory", config)),
        parse_cpu(yq(f"{prefix}.limits.cpu", config)),
        parse_memory(yq(f"{prefix}.limits.memory", config)),
    )


def total(name: str, rows: Iterable[Row]) -> Row:
    """Sum rows into one Row."""
    rows = list(rows)
    return Row(
        name,
        sum(r.cpu_req for r in rows),
        sum(r.mem_req for r in rows),
        sum(r.cpu_lim for r in rows),
        sum(r.mem_lim for r in rows),
    )


def scale(r: Row, factor: int, name: str | None = None) -> Row:
    """Multiply a Row's values (tier/replica counts)."""
    return Row(name or r.name, r.cpu_req * factor, r.mem_req * factor, r.cpu_lim * factor, r.mem_lim * factor)


def yq(query: str, path: str) -> str:
    """
    Run a yq query against a YAML file and return the result as a string.

    Returns:
        str: The query result, stripped of leading/trailing whitespace.

    Raises:
        RuntimeError: If yq is not installed or the query fails.
    """
    try:
        return subprocess.check_output(["yq", "-r", query, path]).decode().strip()
    except FileNotFoundError as exc:
        raise RuntimeError(
            "The 'yq' command is required but was not found in PATH. "
            "Install yq (https://mikefarah.gitbook.io/yq/) and try again."
        ) from exc
    except subprocess.CalledProcessError as exc:
        raise RuntimeError(
            f"Failed to execute yq query {query!r} on {path!r}. "
            "Ensure the file exists, is valid YAML, and that the query is correct."
        ) from exc


def parse_cpu(s: str) -> int:
    """
    Parse a Kubernetes CPU string to millicores.

    Returns:
        int: CPU value in millicores.
    """
    s = s.strip()
    if s.endswith("m"):
        return int(s[:-1])
    return int(float(s) * 1000)


def parse_memory(s: str) -> int:
    """
    Parse a Kubernetes memory string to bytes.

    Returns:
        int: Memory value in bytes.
    """
    s = s.strip()
    if s.endswith("Gi"):
        return int(float(s[:-2]) * 1024**3)
    if s.endswith("G"):
        return int(float(s[:-1]) * 1000**3)
    if s.endswith("Mi"):
        return int(float(s[:-2]) * 1024**2)
    if s.endswith("M"):
        return int(float(s[:-1]) * 1000**2)
    if s.endswith("Ki"):
        return int(float(s[:-2]) * 1024)
    return int(float(s))


def fmt_cpu(millicores: int) -> str:
    """
    Format a millicores value as a human-readable CPU string.

    Returns:
        str: e.g. ``"2"`` for 2000m, ``"500m"`` for 500m.
    """
    if millicores >= 1000 and millicores % 1000 == 0:  # ruff:ignore[magic-value-comparison]
        return f"{millicores // 1000}"
    return f"{millicores}m"


def fmt_mem(b: int) -> str:
    """
    Format a bytes value as a human-readable memory string.

    Returns:
        str: e.g. ``"4Gi"`` for 4 GiB, ``"512Mi"`` for 512 MiB.
    """
    gib = b / 1024**3
    if gib >= 1 and b % (1024**3) == 0:
        return f"{int(gib)}Gi"
    if gib >= 1:
        return f"{gib:.1f}Gi"
    return f"{int(b / 1024**2)}Mi"


# Values written in millicores/MiB; row_mib converts.

# Sidecar resources are hardcoded in pre_spawn_hook.py _*_container() — keep in sync if those change.
SIDECARS = [
    row_mib("proxy", 10, 32, 100, 64),
    row_mib("auth", 10, 48, 100, 96),
    row_mib("api (dashboard)", 50, 128, 250, 512),
    row_mib("s3sync", 10, 64, 200, 256),
]

TIERS = [1, 2, 4]

# MDRepo upload job resources are hardcoded in upload/submission.py — keep in sync.
UPLOAD_JOB = row_mib("uploader", 100, 128, 500, 256)

# s3-sync sidecar per mdrun job, hardcoded in mdrun-api/k8s_client.py — keep in sync.
JOB_S3SYNC = row_mib("s3-sync sidecar", 100, 128, 200, 256)

# Fixed platform overhead in the hub namespace, set in helm/charts/mddash/values.yaml.tmpl — keep in sync with
# proxy.chp.resources and landing.resources there.
CHP_PROXY = row_mib("chp proxy", 100, 128, 500, 512)
LANDING = row_mib("landing page", 50, 32, 100, 64)


def compute_budget(config: str) -> dict:
    """Read the config and compute all per-namespace resource totals."""
    b: dict = {"config": config, "namespace": yq(".namespace", config), "gpu_type": yq('.gpuType // ""', config)}
    b["sidecars"] = SIDECARS

    b["singleuser"] = Row(
        "singleuser (jupyter)",
        parse_cpu(yq(".resources.singleuser.cpu.guarantee", config)),
        parse_memory(yq(".resources.singleuser.memory.guarantee", config)),
        parse_cpu(yq(".resources.singleuser.cpu.limit", config)),
        parse_memory(yq(".resources.singleuser.memory.limit", config)),
    )
    b["notebook"] = Row(
        "jupyter",
        parse_cpu(yq(".resources.notebook.cpuRequest", config)),
        parse_memory(yq(".resources.notebook.memoryRequest", config)),
        parse_cpu(yq(".resources.notebook.cpuLimit", config)),
        parse_memory(yq(".resources.notebook.memoryLimit", config)),
    )
    b["max_notebooks"] = int(yq(".resources.notebookQuota.maxConcurrent", config))
    b["analysis"] = Row(
        "analysis",
        parse_cpu(yq(".resources.analysisJob.cpuRequest", config)),
        parse_memory(yq(".resources.analysisJob.memoryRequest", config)),
        parse_cpu(yq(".resources.analysisJob.cpuLimit", config)),
        parse_memory(yq(".resources.analysisJob.memoryLimit", config)),
    )
    b["ns_quota_configured"] = {
        "requestsCpu": yq(".resources.namespaceQuota.requestsCpu", config),
        "requestsMemory": yq(".resources.namespaceQuota.requestsMemory", config),
        "limitsCpu": yq(".resources.namespaceQuota.limitsCpu", config),
        "limitsMemory": yq(".resources.namespaceQuota.limitsMemory", config),
    }

    # User namespace totals, worst case: all notebooks at the highest tier
    max_tier = b["max_tier"] = max(TIERS)
    b["tiers"] = TIERS
    b["user_tier_rows"] = [(t, scale(b["notebook"], t)) for t in TIERS]
    b["user_pod_total"] = total("User pod total", [*SIDECARS, b["singleuser"]])
    b["user_total"] = total(
        f"USER NAMESPACE TOTAL (worst-case: {max_tier}x)",
        [b["user_pod_total"], scale(b["notebook"], max_tier * b["max_notebooks"]), b["analysis"], UPLOAD_JOB],
    )

    # Hub namespace
    b["ray_worker_replicas"] = int(yq(".tuner.worker.maxReplicas", config))
    b["hub_services"] = [
        row_cfg("jupyterhub-hub", config, ".hub.resources"),
        row_cfg("mdrun-api", config, ".mdrunApi.resources"),
        row_cfg("mdrun-api poller", config, ".mdrunApi.polling.resources"),
        row_cfg("tuner-api", config, ".tuner.api.resources"),
        row_cfg("ray-head", config, ".tuner.ray.head.resources"),
        scale(
            row_cfg("ray-worker", config, ".tuner.worker.resources"),
            b["ray_worker_replicas"],
            f"ray-worker (x {b['ray_worker_replicas']})",
        ),
        CHP_PROXY,
        LANDING,
    ]
    b["services_total"] = total("Services total", b["hub_services"])

    b["max_jobs"] = int(yq(".mdrunApi.jobHeadroom.maxConcurrentJobs", config))
    gmx_cpu = parse_cpu(yq(".mdrunApi.jobHeadroom.cpuPerJob", config))
    gmx_mem = parse_memory(yq(".mdrunApi.jobHeadroom.memoryPerJob", config))
    # GROMACS jobs have request = limit (MPI: throttling causes rank starvation)
    b["job_rows"] = [Row("gromacs  (req=lim)", gmx_cpu, gmx_mem, gmx_cpu, gmx_mem), JOB_S3SYNC]
    b["per_job_total"] = total("Per job total", b["job_rows"])
    b["hub_total"] = total("HUB NAMESPACE TOTAL", [b["services_total"], scale(b["per_job_total"], b["max_jobs"])])

    return b


COL = 36
W = 13


def header() -> None:
    """Print the resource table column headers."""
    print(f"  {'Container':<{COL}} {'CPU req':>{W}} {'Mem req':>{W}} {'CPU lim':>{W}} {'Mem lim':>{W}}")
    print("  " + "─" * (COL + W * 4 + 4))


def row(r: Row, indent: int = 0) -> None:
    """Print a single resource table row."""
    prefix = "  " + "  " * indent
    pad = COL - len("  " * indent)
    print(
        f"{prefix}{r.name:<{pad}} {fmt_cpu(r.cpu_req):>{W}} {fmt_mem(r.mem_req):>{W}} {fmt_cpu(r.cpu_lim):>{W}} {fmt_mem(r.mem_lim):>{W}}"
    )


def subtotal(r: Row) -> None:
    """Print a subtotal row preceded by a separator line."""
    print("  " + "─" * (COL + W * 4 + 4))
    row(r)


def section(title: str) -> None:
    """Print a section heading followed by the column headers."""
    print(f"\n  {title}")
    header()


def compare_quota(label: str, recommended: int, configured_str: str, is_cpu: bool) -> bool:
    """
    Print a quota comparison line and return True if the configured value meets the recommendation.

    Returns:
        bool: True if configured value >= recommended, False otherwise.
    """
    parse = parse_cpu if is_cpu else parse_memory
    fmt = fmt_cpu if is_cpu else fmt_mem
    ok = parse(configured_str) >= recommended
    mark = "✓" if ok else "✗  ← configured value is too low!"
    print(f"    {label:<24} configured={configured_str:<12} recommended≥{fmt(recommended):<12} {mark}")
    return ok


def print_table(b: dict) -> None:
    """Print the human-readable resource budget table."""
    print(f"\nResource Budget — {b['config']}")
    print("=" * 72)

    print(f"\n  ── User namespace (per user, MAX_NOTEBOOKS={b['max_notebooks']}) ──")

    section("User pod  (always-on, 1 pod per user)")
    for r in b["sidecars"]:
        row(r, indent=1)
    row(b["singleuser"], indent=1)
    subtotal(b["user_pod_total"])

    tiers = b["tiers"]
    print(f"\n  Notebook pod  (on-demand, up to {b['max_notebooks']} pods, tiers: {', '.join(f'{t}x' for t in tiers)})")
    for t, sc in b["user_tier_rows"]:
        section(f"  Tier {t}x")
        row(sc, indent=2)
        subtotal(sc._replace(name=f"Per notebook ({t}x)"))

    if b["gpu_type"]:
        print(f"\n  GPU: 1x {b['gpu_type']} (optional, added to notebook container when enabled)")

    section("Analysis job  (on-demand, 1 at a time)")
    row(b["analysis"], indent=1)

    section("MDRepo upload job  (on-demand, 1 at a time)")
    row(UPLOAD_JOB, indent=1)

    print()
    print("  " + "═" * (COL + W * 4 + 4))
    row(b["user_total"])

    print()
    print("  User namespace quota comparison (worst-case: all notebooks at highest tier):")
    ut = b["user_total"]
    cfg = b["ns_quota_configured"]
    ok_u = all([
        compare_quota("NS_REQUESTS_CPU", ut.cpu_req, cfg["requestsCpu"], True),
        compare_quota("NS_REQUESTS_MEMORY", ut.mem_req, cfg["requestsMemory"], False),
        compare_quota("NS_LIMITS_CPU", ut.cpu_lim, cfg["limitsCpu"], True),
        compare_quota("NS_LIMITS_MEMORY", ut.mem_lim, cfg["limitsMemory"], False),
    ])
    if not ok_u:
        print("\n  WARNING: Increase the under-provisioned values in resources.namespaceQuota and redeploy.")

    print("\n\n  ── Hub namespace ──")

    section("Always-on services")
    for r in b["hub_services"]:
        row(r, indent=1)
    subtotal(b["services_total"])

    section(f"HPC jobs  (on-demand, up to {b['max_jobs']} concurrent)")
    for r in b["job_rows"]:
        row(r, indent=1)
    subtotal(b["per_job_total"])

    print()
    print("  " + "═" * (COL + W * 4 + 4))
    row(b["hub_total"])
    print(f"\n  Set these as the Rancher quota for the hub namespace ({b['namespace']}).")
    print()


def print_json(b: dict) -> None:
    """Print hub-namespace quota totals as JSON (consumed by install.sh)."""
    ht = b["hub_total"]
    hub = {
        "requestsCpu": fmt_cpu(ht.cpu_req),
        "requestsMemory": fmt_mem(ht.mem_req),
        "limitsCpu": fmt_cpu(ht.cpu_lim),
        "limitsMemory": fmt_mem(ht.mem_lim),
    }
    print(json.dumps({"hub": hub}))


def main(argv: list[str]) -> None:
    json_mode = "--json" in argv
    args = [a for a in argv if a != "--json"]
    if len(args) != 1:
        print(f"Usage: {sys.argv[0]} [--json] <config.yaml>", file=sys.stderr)
        sys.exit(1)
    budget = compute_budget(args[0])
    if json_mode:
        print_json(budget)
    else:
        print_table(budget)


if __name__ == "__main__":
    main(sys.argv[1:])
