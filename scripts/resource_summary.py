#!/usr/bin/env python3
"""
Offline resource budget calculator for mddash namespaces.

Reads resource configuration from config YAML files and computes the
recommended namespace quota values for both the hub namespace and
per-user namespaces.

Usage:
    python3 scripts/resource_summary.py <config.yaml> <mdrun-api-values.yaml>

Example:
    python3 scripts/resource_summary.py config.dev.yaml helm/charts/mdrun-api/values.dev.yaml
    python3 scripts/resource_summary.py config.yaml     helm/charts/mdrun-api/values.yaml
"""

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
    if millicores >= 1000 and millicores % 1000 == 0:  # noqa: PLR2004
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


def main(config: str, mdrun_values: str) -> None:  # noqa: PLR0914
    """Print a full resource budget summary for both user and hub namespaces."""
    print(f"\nResource Budget — {config}")
    print("=" * 72)

    # ── User namespace ─────────────────────────────────────────────────────────

    # Sidecar resources are hardcoded in pre_spawn_hook.py _*_container() — keep in sync if those change.
    # CPU in millicores, memory in MiB.
    sidecars = [
        ("proxy", 10, 32, 100, 64),
        ("auth", 10, 48, 100, 96),
        ("api (dashboard)", 50, 128, 250, 512),
        ("s3sync", 10, 64, 200, 256),
    ]

    su_cpu_req = parse_cpu(yq(".resources.singleuser.cpu.guarantee", config))
    su_mem_req = parse_memory(yq(".resources.singleuser.memory.guarantee", config))
    su_cpu_lim = parse_cpu(yq(".resources.singleuser.cpu.limit", config))
    su_mem_lim = parse_memory(yq(".resources.singleuser.memory.limit", config))

    # Base notebook resources (1x tier)
    nb_cpu_req = parse_cpu(yq(".resources.notebook.cpuRequest", config))
    nb_mem_req = parse_memory(yq(".resources.notebook.memoryRequest", config))
    nb_cpu_lim = parse_cpu(yq(".resources.notebook.cpuLimit", config))
    nb_mem_lim = parse_memory(yq(".resources.notebook.memoryLimit", config))
    max_nb = int(yq(".resources.notebookQuota.maxConcurrent", config))

    gpu_type = yq('.gpuType // ""', config)

    an_cpu_req = parse_cpu(yq(".resources.analysisJob.cpuRequest", config))
    an_mem_req = parse_memory(yq(".resources.analysisJob.memoryRequest", config))
    an_cpu_lim = parse_cpu(yq(".resources.analysisJob.cpuLimit", config))
    an_mem_lim = parse_memory(yq(".resources.analysisJob.memoryLimit", config))

    # Tier multipliers
    tiers = [1, 2, 4]
    max_tier = max(tiers)

    print(f"\n  ── User namespace (per user, MAX_NOTEBOOKS={max_nb}) ──")

    section("User pod  (always-on, 1 pod per user)")
    pod_cpu_req = pod_mem_req = pod_cpu_lim = pod_mem_lim = 0
    for name, cr, mr, cl, ml in sidecars:
        mr_b = mr * 1024**2
        ml_b = ml * 1024**2
        row(name, cr, mr_b, cl, ml_b, indent=1)
        pod_cpu_req += cr
        pod_mem_req += mr_b
        pod_cpu_lim += cl
        pod_mem_lim += ml_b
    row("singleuser (jupyter)", su_cpu_req, su_mem_req, su_cpu_lim, su_mem_lim, indent=1)
    pod_cpu_req += su_cpu_req
    pod_mem_req += su_mem_req
    pod_cpu_lim += su_cpu_lim
    pod_mem_lim += su_mem_lim
    subtotal("User pod total", pod_cpu_req, pod_mem_req, pod_cpu_lim, pod_mem_lim)

    print(f"\n  Notebook pod  (on-demand, up to {max_nb} pods, tiers: {', '.join(f'{t}x' for t in tiers)})")
    for t in tiers:
        section(f"  Tier {t}x")
        t_nb_cr = nb_cpu_req * t
        t_nb_mr = nb_mem_req * t
        t_nb_cl = nb_cpu_lim * t
        t_nb_ml = nb_mem_lim * t
        row("jupyter", t_nb_cr, t_nb_mr, t_nb_cl, t_nb_ml, indent=2)
        subtotal(f"Per notebook ({t}x)", t_nb_cr, t_nb_mr, t_nb_cl, t_nb_ml)

    if gpu_type:
        print(f"\n  GPU: 1x {gpu_type} (optional, added to notebook container when enabled)")

    # Worst-case per notebook (highest tier)
    per_nb_cr = nb_cpu_req * max_tier
    per_nb_mr = nb_mem_req * max_tier
    per_nb_cl = nb_cpu_lim * max_tier
    per_nb_ml = nb_mem_lim * max_tier

    section("Analysis job  (on-demand, 1 at a time)")
    row("analysis", an_cpu_req, an_mem_req, an_cpu_lim, an_mem_lim, indent=1)

    total_u_cr = pod_cpu_req + max_nb * per_nb_cr + an_cpu_req
    total_u_mr = pod_mem_req + max_nb * per_nb_mr + an_mem_req
    total_u_cl = pod_cpu_lim + max_nb * per_nb_cl + an_cpu_lim
    total_u_ml = pod_mem_lim + max_nb * per_nb_ml + an_mem_lim

    print()
    print("  " + "═" * (COL + W * 4 + 4))
    row(f"USER NAMESPACE TOTAL (worst-case: {max_tier}x)", total_u_cr, total_u_mr, total_u_cl, total_u_ml)

    print()
    print("  User namespace quota comparison (worst-case: all notebooks at highest tier):")
    ok_u = all([
        compare_quota("NS_REQUESTS_CPU", total_u_cr, yq(".resources.namespaceQuota.requestsCpu", config), True),
        compare_quota("NS_REQUESTS_MEMORY", total_u_mr, yq(".resources.namespaceQuota.requestsMemory", config), False),
        compare_quota("NS_LIMITS_CPU", total_u_cl, yq(".resources.namespaceQuota.limitsCpu", config), True),
        compare_quota("NS_LIMITS_MEMORY", total_u_ml, yq(".resources.namespaceQuota.limitsMemory", config), False),
    ])
    if not ok_u:
        print("\n  WARNING: Increase the under-provisioned values in resources.namespaceQuota and redeploy.")

    # ── Hub namespace ──────────────────────────────────────────────────────────

    mdrun_cr = parse_cpu(yq(".resources.requests.cpu", mdrun_values))
    mdrun_mr = parse_memory(yq(".resources.requests.memory", mdrun_values))
    mdrun_cl = parse_cpu(yq(".resources.limits.cpu", mdrun_values))
    mdrun_ml = parse_memory(yq(".resources.limits.memory", mdrun_values))

    ta_cr = parse_cpu(yq(".gromacsTuner.api.resources.requests.cpu", config))
    ta_mr = parse_memory(yq(".gromacsTuner.api.resources.requests.memory", config))
    ta_cl = parse_cpu(yq(".gromacsTuner.api.resources.limits.cpu", config))
    ta_ml = parse_memory(yq(".gromacsTuner.api.resources.limits.memory", config))

    rh_cr = parse_cpu(yq(".gromacsTuner.ray.head.resources.requests.cpu", config))
    rh_mr = parse_memory(yq(".gromacsTuner.ray.head.resources.requests.memory", config))
    rh_cl = parse_cpu(yq(".gromacsTuner.ray.head.resources.limits.cpu", config))
    rh_ml = parse_memory(yq(".gromacsTuner.ray.head.resources.limits.memory", config))

    rw_cr = parse_cpu(yq(".gromacsTuner.ray.worker.resources.requests.cpu", config))
    rw_mr = parse_memory(yq(".gromacsTuner.ray.worker.resources.requests.memory", config))
    rw_cl = parse_cpu(yq(".gromacsTuner.ray.worker.resources.limits.cpu", config))
    rw_ml = parse_memory(yq(".gromacsTuner.ray.worker.resources.limits.memory", config))
    rw_replicas = int(yq(".gromacsTuner.ray.worker.maxReplicas", config))

    hub_cr = parse_cpu(yq(".hub.resources.requests.cpu", config))
    hub_mr = parse_memory(yq(".hub.resources.requests.memory", config))
    hub_cl = parse_cpu(yq(".hub.resources.limits.cpu", config))
    hub_ml = parse_memory(yq(".hub.resources.limits.memory", config))

    max_jobs = int(yq(".mdrunApi.jobHeadroom.maxConcurrentJobs", config))
    gmx_cpu = parse_cpu(yq(".mdrunApi.jobHeadroom.cpuPerJob", config))
    gmx_mem = parse_memory(yq(".mdrunApi.jobHeadroom.memoryPerJob", config))

    # s3-sync sidecar per job (fixed, hardcoded in mdrun-api/k8s_client.py)
    s3sync_cr, s3sync_mr = 100, 128 * 1024**2
    s3sync_cl, s3sync_ml = 200, 256 * 1024**2

    # GROMACS jobs have request = limit (MPI: throttling causes rank starvation)
    per_job_cr = gmx_cpu + s3sync_cr
    per_job_mr = gmx_mem + s3sync_mr
    per_job_cl = gmx_cpu + s3sync_cl
    per_job_ml = gmx_mem + s3sync_ml

    print("\n\n  ── Hub namespace ──")

    section("Always-on services")
    row("jupyterhub-hub", hub_cr, hub_mr, hub_cl, hub_ml, indent=1)
    row("mdrun-api", mdrun_cr, mdrun_mr, mdrun_cl, mdrun_ml, indent=1)
    row("gromacs-tuner-api", ta_cr, ta_mr, ta_cl, ta_ml, indent=1)
    row("ray-head", rh_cr, rh_mr, rh_cl, rh_ml, indent=1)
    row(
        f"ray-worker (x {rw_replicas})",
        rw_replicas * rw_cr,
        rw_replicas * rw_mr,
        rw_replicas * rw_cl,
        rw_replicas * rw_ml,
        indent=1,
    )

    svc_cr = hub_cr + mdrun_cr + ta_cr + rh_cr + rw_replicas * rw_cr
    svc_mr = hub_mr + mdrun_mr + ta_mr + rh_mr + rw_replicas * rw_mr
    svc_cl = hub_cl + mdrun_cl + ta_cl + rh_cl + rw_replicas * rw_cl
    svc_ml = hub_ml + mdrun_ml + ta_ml + rh_ml + rw_replicas * rw_ml
    subtotal("Services total", svc_cr, svc_mr, svc_cl, svc_ml)

    section(f"HPC jobs  (on-demand, up to {max_jobs} concurrent)")
    row("gromacs  (req=lim)", gmx_cpu, gmx_mem, gmx_cpu, gmx_mem, indent=1)
    row("s3-sync sidecar", s3sync_cr, s3sync_mr, s3sync_cl, s3sync_ml, indent=1)
    subtotal("Per job total", per_job_cr, per_job_mr, per_job_cl, per_job_ml)

    total_h_cr = svc_cr + max_jobs * per_job_cr
    total_h_mr = svc_mr + max_jobs * per_job_mr
    total_h_cl = svc_cl + max_jobs * per_job_cl
    total_h_ml = svc_ml + max_jobs * per_job_ml

    print()
    print("  " + "═" * (COL + W * 4 + 4))
    row("HUB NAMESPACE TOTAL", total_h_cr, total_h_mr, total_h_cl, total_h_ml)
    print(f"\n  Set these as the Rancher quota for the hub namespace ({yq('.namespace', config)}).")
    print()


if __name__ == "__main__":
    if len(sys.argv) != 3:  # noqa: PLR2004
        print(f"Usage: {sys.argv[0]} <config.yaml> <mdrun-api-values.yaml>", file=sys.stderr)
        sys.exit(1)
    main(sys.argv[1], sys.argv[2])
