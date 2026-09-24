#!/usr/bin/env python3
"""
Offline resource budget calculator for mddash namespaces.

Reads resource configuration from config YAML files and computes the
recommended namespace quota values for both the hub namespace and
per-user namespaces.

Usage:
    python3 scripts/resource_summary.py <config.yaml>          # human-readable table
    python3 scripts/resource_summary.py --json <config.yaml>   # totals as JSON (for install.sh)

Example:
    make resources ENV=dev
    python3 scripts/resource_summary.py config.dev.yaml
"""

import json
import subprocess
import sys


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


# Sidecar resources are hardcoded in pre_spawn_hook.py _*_container() — keep in sync if those change.
# CPU in millicores, memory in MiB.
SIDECARS = [
    ("proxy", 10, 32, 100, 64),
    ("auth", 10, 48, 100, 96),
    ("api (dashboard)", 50, 128, 250, 512),
    ("s3sync", 10, 64, 200, 256),
]

TIERS = [1, 2, 4]

# MDRepo upload job resources are hardcoded in upload/submission.py (100m/128Mi req, 500m/256Mi lim).
UPLOAD_JOB = ("uploader", 100, 128, 500, 256)

# s3-sync sidecar per mdrun job (fixed, hardcoded in mdrun-api/k8s_client.py)
JOB_S3SYNC = ("s3-sync sidecar", 100, 128, 200, 256)

# Fixed platform overhead in the hub namespace, set in helm/charts/mddash/values.yaml.tmpl — keep in sync with
# proxy.chp.resources and landing.resources there. CPU in millicores, memory in MiB.
CHP_PROXY = ("chp proxy", 100, 128, 500, 512)
LANDING = ("landing page", 50, 32, 100, 64)


def compute_budget(config: str) -> dict:
    """Read the config and compute all per-namespace resource totals."""
    b: dict = {"config": config, "namespace": yq(".namespace", config), "gpu_type": yq('.gpuType // ""', config)}
    b["sidecars"] = [(name, cr, mr * 1024**2, cl, ml * 1024**2) for name, cr, mr, cl, ml in SIDECARS]

    b["singleuser"] = (
        "singleuser (jupyter)",
        parse_cpu(yq(".resources.singleuser.cpu.guarantee", config)),
        parse_memory(yq(".resources.singleuser.memory.guarantee", config)),
        parse_cpu(yq(".resources.singleuser.cpu.limit", config)),
        parse_memory(yq(".resources.singleuser.memory.limit", config)),
    )

    b["notebook"] = (
        "jupyter",
        parse_cpu(yq(".resources.notebook.cpuRequest", config)),
        parse_memory(yq(".resources.notebook.memoryRequest", config)),
        parse_cpu(yq(".resources.notebook.cpuLimit", config)),
        parse_memory(yq(".resources.notebook.memoryLimit", config)),
    )
    b["max_notebooks"] = int(yq(".resources.notebookQuota.maxConcurrent", config))
    b["tiers"] = TIERS

    b["analysis"] = (
        "analysis",
        parse_cpu(yq(".resources.analysisJob.cpuRequest", config)),
        parse_memory(yq(".resources.analysisJob.memoryRequest", config)),
        parse_cpu(yq(".resources.analysisJob.cpuLimit", config)),
        parse_memory(yq(".resources.analysisJob.memoryLimit", config)),
    )
    b["upload_job"] = (UPLOAD_JOB[0], UPLOAD_JOB[1], UPLOAD_JOB[2] * 1024**2, UPLOAD_JOB[3], UPLOAD_JOB[4] * 1024**2)

    b["ns_quota_configured"] = {
        "requestsCpu": yq(".resources.namespaceQuota.requestsCpu", config),
        "requestsMemory": yq(".resources.namespaceQuota.requestsMemory", config),
        "limitsCpu": yq(".resources.namespaceQuota.limitsCpu", config),
        "limitsMemory": yq(".resources.namespaceQuota.limitsMemory", config),
    }

    # ── User namespace totals (worst case: all notebooks at highest tier) ──
    pod = [0, 0, 0, 0]
    for _, cr, mr, cl, ml in b["sidecars"]:
        pod[0] += cr
        pod[1] += mr
        pod[2] += cl
        pod[3] += ml
    for i, v in enumerate(b["singleuser"][1:]):
        pod[i] += v
    b["user_pod_total"] = ("User pod total", *pod)

    max_tier = max(TIERS)
    nb = b["notebook"][1:]
    per_nb = [v * max_tier for v in nb]
    b["user_tier_rows"] = [(t, [v * t for v in nb]) for t in TIERS]
    b["max_tier"] = max_tier

    an = b["analysis"][1:]
    up = b["upload_job"][1:]
    b["user_total"] = (
        f"USER NAMESPACE TOTAL (worst-case: {max_tier}x)",
        pod[0] + b["max_notebooks"] * per_nb[0] + an[0] + up[0],
        pod[1] + b["max_notebooks"] * per_nb[1] + an[1] + up[1],
        pod[2] + b["max_notebooks"] * per_nb[2] + an[2] + up[2],
        pod[3] + b["max_notebooks"] * per_nb[3] + an[3] + up[3],
    )

    # ── Hub namespace ──
    b["hub_services"] = [
        (
            "jupyterhub-hub",
            parse_cpu(yq(".hub.resources.requests.cpu", config)),
            parse_memory(yq(".hub.resources.requests.memory", config)),
            parse_cpu(yq(".hub.resources.limits.cpu", config)),
            parse_memory(yq(".hub.resources.limits.memory", config)),
        ),
        (
            "mdrun-api",
            parse_cpu(yq(".mdrunApi.resources.requests.cpu", config)),
            parse_memory(yq(".mdrunApi.resources.requests.memory", config)),
            parse_cpu(yq(".mdrunApi.resources.limits.cpu", config)),
            parse_memory(yq(".mdrunApi.resources.limits.memory", config)),
        ),
        (
            "mdrun-api poller",
            parse_cpu(yq(".mdrunApi.polling.resources.requests.cpu", config)),
            parse_memory(yq(".mdrunApi.polling.resources.requests.memory", config)),
            parse_cpu(yq(".mdrunApi.polling.resources.limits.cpu", config)),
            parse_memory(yq(".mdrunApi.polling.resources.limits.memory", config)),
        ),
        (
            "tuner-api",
            parse_cpu(yq(".tuner.api.resources.requests.cpu", config)),
            parse_memory(yq(".tuner.api.resources.requests.memory", config)),
            parse_cpu(yq(".tuner.api.resources.limits.cpu", config)),
            parse_memory(yq(".tuner.api.resources.limits.memory", config)),
        ),
        (
            "ray-head",
            parse_cpu(yq(".tuner.ray.head.resources.requests.cpu", config)),
            parse_memory(yq(".tuner.ray.head.resources.requests.memory", config)),
            parse_cpu(yq(".tuner.ray.head.resources.limits.cpu", config)),
            parse_memory(yq(".tuner.ray.head.resources.limits.memory", config)),
        ),
    ]
    rw = [
        parse_cpu(yq(".tuner.worker.resources.requests.cpu", config)),
        parse_memory(yq(".tuner.worker.resources.requests.memory", config)),
        parse_cpu(yq(".tuner.worker.resources.limits.cpu", config)),
        parse_memory(yq(".tuner.worker.resources.limits.memory", config)),
    ]
    b["ray_worker_replicas"] = int(yq(".tuner.worker.maxReplicas", config))
    b["hub_services"].append((
        "ray-worker (x {})".format(b["ray_worker_replicas"]),
        *[v * b["ray_worker_replicas"] for v in rw],
    ))
    b["hub_services"].extend(
        (name, cr, mr * 1024**2, cl, ml * 1024**2) for name, cr, mr, cl, ml in (CHP_PROXY, LANDING)
    )

    svc = [0, 0, 0, 0]
    for _, cr, mr, cl, ml in b["hub_services"]:
        svc[0] += cr
        svc[1] += mr
        svc[2] += cl
        svc[3] += ml
    b["services_total"] = ("Services total", *svc)

    b["max_jobs"] = int(yq(".mdrunApi.jobHeadroom.maxConcurrentJobs", config))
    gmx = [
        parse_cpu(yq(".mdrunApi.jobHeadroom.cpuPerJob", config)),
        parse_memory(yq(".mdrunApi.jobHeadroom.memoryPerJob", config)),
    ]
    # GROMACS jobs have request = limit (MPI: throttling causes rank starvation)
    b["job_rows"] = [("gromacs  (req=lim)", gmx[0], gmx[1], gmx[0], gmx[1])]
    s3 = (JOB_S3SYNC[0], JOB_S3SYNC[1], JOB_S3SYNC[2] * 1024**2, JOB_S3SYNC[3], JOB_S3SYNC[4] * 1024**2)
    b["job_rows"].append(s3)
    b["per_job_total"] = ("Per job total", gmx[0] + s3[1], gmx[1] + s3[2], gmx[0] + s3[3], gmx[1] + s3[4])

    pj = b["per_job_total"][1:]
    b["hub_total"] = (
        "HUB NAMESPACE TOTAL",
        svc[0] + b["max_jobs"] * pj[0],
        svc[1] + b["max_jobs"] * pj[1],
        svc[2] + b["max_jobs"] * pj[2],
        svc[3] + b["max_jobs"] * pj[3],
    )

    return b


COL = 36
W = 13


def header() -> None:
    """Print the resource table column headers."""
    print(f"  {'Container':<{COL}} {'CPU req':>{W}} {'Mem req':>{W}} {'CPU lim':>{W}} {'Mem lim':>{W}}")
    print("  " + "─" * (COL + W * 4 + 4))


def row(label: str, cr: int, mr: int, cl: int, ml: int, indent: int = 0) -> None:
    """Print a single resource table row."""
    prefix = "  " + "  " * indent
    pad = COL - len("  " * indent)
    print(f"{prefix}{label:<{pad}} {fmt_cpu(cr):>{W}} {fmt_mem(mr):>{W}} {fmt_cpu(cl):>{W}} {fmt_mem(ml):>{W}}")


def subtotal(label: str, cr: int, mr: int, cl: int, ml: int) -> None:
    """Print a subtotal row preceded by a separator line."""
    print("  " + "─" * (COL + W * 4 + 4))
    row(label, cr, mr, cl, ml)


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
    for name, cr, mr, cl, ml in b["sidecars"]:
        row(name, cr, mr, cl, ml, indent=1)
    su = b["singleuser"]
    row(su[0], su[1], su[2], su[3], su[4], indent=1)
    pod = b["user_pod_total"]
    subtotal(pod[0], pod[1], pod[2], pod[3], pod[4])

    tiers = b["tiers"]
    print(f"\n  Notebook pod  (on-demand, up to {b['max_notebooks']} pods, tiers: {', '.join(f'{t}x' for t in tiers)})")
    for t, vals in b["user_tier_rows"]:
        section(f"  Tier {t}x")
        row("jupyter", vals[0], vals[1], vals[2], vals[3], indent=2)
        subtotal(f"Per notebook ({t}x)", vals[0], vals[1], vals[2], vals[3])

    if b["gpu_type"]:
        print(f"\n  GPU: 1x {b['gpu_type']} (optional, added to notebook container when enabled)")

    section("Analysis job  (on-demand, 1 at a time)")
    an = b["analysis"]
    row(an[0], an[1], an[2], an[3], an[4], indent=1)

    section("MDRepo upload job  (on-demand, 1 at a time)")
    up = b["upload_job"]
    row(up[0], up[1], up[2], up[3], up[4], indent=1)

    print()
    print("  " + "═" * (COL + W * 4 + 4))
    ut = b["user_total"]
    row(ut[0], ut[1], ut[2], ut[3], ut[4])

    print()
    print("  User namespace quota comparison (worst-case: all notebooks at highest tier):")
    cfg = b["ns_quota_configured"]
    ok_u = all([
        compare_quota("NS_REQUESTS_CPU", ut[1], cfg["requestsCpu"], True),
        compare_quota("NS_REQUESTS_MEMORY", ut[2], cfg["requestsMemory"], False),
        compare_quota("NS_LIMITS_CPU", ut[3], cfg["limitsCpu"], True),
        compare_quota("NS_LIMITS_MEMORY", ut[4], cfg["limitsMemory"], False),
    ])
    if not ok_u:
        print("\n  WARNING: Increase the under-provisioned values in resources.namespaceQuota and redeploy.")

    print("\n\n  ── Hub namespace ──")

    section("Always-on services")
    for name, cr, mr, cl, ml in b["hub_services"]:
        row(name, cr, mr, cl, ml, indent=1)
    svc = b["services_total"]
    subtotal(svc[0], svc[1], svc[2], svc[3], svc[4])

    section(f"HPC jobs  (on-demand, up to {b['max_jobs']} concurrent)")
    for name, cr, mr, cl, ml in b["job_rows"]:
        row(name, cr, mr, cl, ml, indent=1)
    pj = b["per_job_total"]
    subtotal(pj[0], pj[1], pj[2], pj[3], pj[4])

    print()
    print("  " + "═" * (COL + W * 4 + 4))
    ht = b["hub_total"]
    row(ht[0], ht[1], ht[2], ht[3], ht[4])
    print(f"\n  Set these as the Rancher quota for the hub namespace ({b['namespace']}).")
    print()


def quota_values(total: tuple) -> dict:
    """Convert a (label, cpu_req, mem_req, cpu_lim, mem_lim) total row to quota strings."""
    return {
        "requestsCpu": fmt_cpu(total[1]),
        "requestsMemory": fmt_mem(total[2]),
        "limitsCpu": fmt_cpu(total[3]),
        "limitsMemory": fmt_mem(total[4]),
    }


def print_json(b: dict) -> None:
    """Print per-namespace quota totals as JSON (consumed by install.sh)."""
    print(json.dumps({"hub": quota_values(b["hub_total"]), "user": quota_values(b["user_total"])}))


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
