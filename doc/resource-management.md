# Resource Management

This document explains the resource budget model for user namespaces, how to calculate the correct quota values, and how to configure them.

## Namespace structure

Each user gets an isolated Kubernetes namespace (`{helm-package}-user-{username}-ns`) managed by JupyterHub's pre-spawn hook. Two categories of workload run there:

| Category | Lifetime | Examples |
|---|---|---|
| Always-on | While the user is logged in | JupyterHub singleuser pod + sidecars (proxy, auth, api, s3sync) |
| On-demand | User-initiated, short to long-lived | Notebook pods, analysis jobs |

All resource quotas below refer to this **user namespace**. The hub namespace (`md-dashboard-ns`) hosts JupyterHub itself, mdrun-api, and the GROMACS tuner — those are not covered by per-user quotas.

---

## Fixed overhead (always-on)

These containers are present for every logged-in user.

### JupyterHub singleuser container

| | CPU | Memory |
|---|---|---|
| Request | 200m | 512Mi |
| Limit | 1000m | 4Gi |

Configured via `resources.singleuser` in `config.yaml`.

### Sidecar containers (hardcoded in `pre_spawn_hook.py`)

| Container | CPU req | Mem req | CPU lim | Mem lim |
|---|---|---|---|---|
| proxy (Caddy) | 10m | 32Mi | 100m | 64Mi |
| auth | 10m | 48Mi | 100m | 96Mi |
| api (dashboard) | 50m | 128Mi | 250m | 512Mi |
| s3sync | 10m | 64Mi | 200m | 256Mi |
| **Sidecar total** | **80m** | **272Mi** | **650m** | **928Mi** |

**Fixed overhead total:** ~280m CPU / ~784Mi memory (requests) · ~1650m CPU / ~4.9Gi (limits)

---

## On-demand workloads

### Notebook pods

Each notebook pod consists of two containers. Resources are configured via `resources.notebook` in `config.yaml` and flow through the Helm chart into the API sidecar's environment.

| Container | CPU req | Mem req | CPU lim | Mem lim |
|---|---|---|---|---|
| jupyter | 200m | 512Mi | 2000m | 4Gi |
| gmx | 100m | 256Mi | 2000m | 2Gi |
| **Per notebook** | **300m** | **768Mi** | **4000m** | **6Gi** |

**Why gmx has a high CPU limit:** GROMACS is run with MPI/OpenMP inside this container. CPU throttling causes rank starvation and produces incorrect simulation results. The limit is set high relative to the request to allow full CPU burst during simulations without scheduling burdens from a large guaranteed reservation.

**Why jupyter limits are generous:** Jupyter notebooks run user-written Python code that can spike in memory (e.g. loading a large trajectory). A hard limit of 4Gi prevents a runaway computation from OOMKilling other pods, while still allowing reasonable burst.

The maximum number of concurrent notebook pods per user is controlled by `resources.notebookQuota.maxConcurrent` in `config.yaml`. The API enforces this limit proactively before attempting pod creation.

### Analysis jobs

| | CPU | Memory |
|---|---|---|
| Request | 1000m | 2Gi |
| Limit | 4000m | 8Gi |

These are batch jobs (mddb_wf) that run to completion and are then deleted. Only one analysis job per experiment can be active at a time (enforced by job naming).

---

## Quota formula

The namespace quota values (`NS_REQUESTS_CPU`, `NS_LIMITS_CPU`, etc.) should be set to cover simultaneous full load:

```
# fixed_base = sidecars + JupyterHub singleuser (always-on, 80m+200m = 280m / 272Mi+512Mi = 784Mi)
requests_cpu = fixed_base (280m)
             + MAX_NOTEBOOKS × 300m
             + analysis_headroom (1000m)

requests_mem = fixed_base (784Mi)
             + MAX_NOTEBOOKS × 768Mi
             + analysis_headroom (2Gi)

limits_cpu   = sidecar_base (650m)
             + singleuser (1000m)
             + MAX_NOTEBOOKS × 4000m
             + analysis_limit (4000m)

limits_mem   = sidecar_base (928Mi)
             + singleuser (4Gi)
             + MAX_NOTEBOOKS × 6Gi
             + analysis_limit (8Gi)
```

### With `MAX_NOTEBOOKS = 2` (default)

| | Requests (from formula) | Limits (from formula) |
|---|---|---|
| CPU | ~1880m | ~13650m |
| Memory | ~4.3Gi | ~25Gi |

Set `resources.namespaceQuota.*` in `config.dev.yaml` / `config.yaml` to values ≥ these formula minimums, rounded up to your node size and multi-tenancy requirements.

---

## Requests vs limits

| Concept | Purpose | Behavior on breach |
|---|---|---|
| Request | Scheduler placement; proportional CPU share under contention | Pod not scheduled if node lacks capacity |
| Limit | Hard per-container ceiling | CPU → throttled (silent slowdown); Memory → OOMKill |
| Namespace requests quota | Cluster-level scheduling budget | Pod creation rejected (403) if quota exhausted |
| Namespace limits quota | Hard ceiling across all containers | Pod creation rejected (403) if quota exhausted |

**Key insight:** Namespace limits quota must be ≥ sum of all container limits at full load. If it is smaller than this sum, users will hit 403 errors even when pods are within their individual limits. The formula above ensures consistency.

---

## Setting quotas in Rancher

1. Edit `resources.namespaceQuota.*` in `config.yaml` (or `config.dev.yaml` for dev).
2. Run `make deploy` — the template renders these values into the hub's `extraEnv`, which the pre-spawn hook reads when creating user namespaces.
3. **Existing user namespaces** are only updated when the user logs out and back in (the pre-spawn hook recreates the namespace quota annotation on next login). To force immediate update, patch the namespace annotation manually or delete the namespace (it will be recreated on next login).

### Using `make resources`

```
make resources        # uses ENV=dev (current branch)
make resources ENV=prod
```

Output shows:
1. Per-component resource breakdown (user pod, notebooks, analysis jobs, hub services)
2. Recommended namespace quota minimums from the formula
3. A comparison against the configured `resources.namespaceQuota.*` values

Use this before setting Rancher quotas to verify the configured values cover the formula minimums.

---

## Notebook resource tiers

Users can choose between three resource tiers when starting a notebook: **1x** (base), **2x**, and **4x**. Tiers are multipliers applied to the base resource values defined in `config.yaml`. An optional **GPU toggle** attaches a single GPU to the gmx sidecar container.

### How tiers work

The base resources in `resources.notebook` (cpuRequest, memoryRequest, etc.) represent the 1x tier. The API multiplies all CPU and memory values by the tier factor at runtime. No per-tier configuration in config.yaml is needed.

| Tier | CPU multiplier | Memory multiplier |
|------|---------------|------------------|
| 1x | 1× | 1× |
| 2x | 2× | 2× |
| 4x | 4× | 4× |

### GPU support

The UI always shows a GPU checkbox. When enabled, the GPU resource defined by the `gpuType` config key (rendered to the `GPU_TYPE` environment variable, e.g. `nvidia.com/mig-1g.10gb`) is added to the gmx container's requests and limits as `"1"`. GPU is independent of the tier selection.

### Updated quota formula

The namespace quota must cover the **worst case**: all `MAX_NOTEBOOKS` at the highest tier (4x):

```
requests_cpu = fixed_base (280m)
             + MAX_NOTEBOOKS × 4 × (base_nb_req + base_gmx_req)
             + analysis_headroom (1000m)

limits_cpu   = sidecar_base (650m)
             + singleuser (1000m)
             + MAX_NOTEBOOKS × 4 × (base_nb_lim + base_gmx_lim)
             + analysis_limit (4000m)
```

GPU resources use a separate Kubernetes resource name and do not count toward CPU/memory quota.

### Pod labels

Notebook pods carry `tier` and `gpu` labels alongside the existing `type: notebook`:

```yaml
labels:
  type: notebook
  tier: "2x"
  gpu: "false"
```

### Database columns

The `notebooks` table has `tier` (enum: 1x, 2x, 4x) and `gpu` (boolean) columns so the frontend can display the active tier for a running notebook.

### API endpoints

- `POST /api/.../notebook` — accepts optional `{"tier": "2x", "gpu": true}` JSON body
- `GET /api/.../notebook-config` — returns available tiers and the default tier
