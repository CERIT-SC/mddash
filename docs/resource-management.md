# Resource Management

## Namespace structure

Each user gets an isolated Kubernetes namespace (`{helm-package}-user-{username}-ns`) managed by JupyterHub's pre-spawn hook. Two categories of workload run there:

| Category | Lifetime | Examples |
|---|---|---|
| Always-on | While the user is logged in | JupyterHub singleuser pod + sidecars (proxy, auth, api, s3sync) |
| On-demand | User-initiated, short to long-lived | Notebook pods, analysis jobs |

The hub namespace (`md-dashboard-ns`) hosts JupyterHub itself, mdrun-api, and the GROMACS tuner — those are not covered by per-user quotas.

---

## Fixed overhead (always-on)

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

Resources are configured via `resources.notebook` in `config.yaml`.

| Container | CPU req | Mem req | CPU lim | Mem lim |
|---|---|---|---|---|
| jupyter | 500m | 1Gi | 5000m | 8Gi |
| gmx | 100m | 256Mi | 4000m | 8Gi |
| **Per notebook** | **600m** | **~1.25Gi** | **9000m** | **16Gi** |

**Why gmx has a high CPU limit:** GROMACS is run with MPI/OpenMP inside this container. CPU throttling causes rank starvation and produces incorrect simulation results.

**Why jupyter limits are generous:** User notebooks can spike in memory (e.g. loading a large trajectory). The 8Gi limit prevents a runaway computation from OOMKilling other pods.

`resources.notebookQuota.maxConcurrent` sets the API-enforced count limit on concurrent notebook pods. It is sized so that `maxConcurrent` notebooks at the **4x tier** fit within the namespace quota — the same quota headroom fits `maxConcurrent × 4` notebooks at 1x tier.

### Analysis jobs

| | CPU | Memory |
|---|---|---|
| Request | 1000m | 2Gi |
| Limit | 4000m | 8Gi |

Batch jobs (mddb_wf). Only one analysis job per experiment can be active at a time (enforced by job naming).

---

## Quota formula

```
# fixed_base = sidecars + singleuser = 280m CPU / 784Mi memory
requests_cpu = fixed_base (280m)     + MAX_NOTEBOOKS × 600m    + analysis (1000m)
requests_mem = fixed_base (784Mi)    + MAX_NOTEBOOKS × 1280Mi  + analysis (2Gi)
limits_cpu   = fixed_base (1650m)    + MAX_NOTEBOOKS × 9000m   + analysis (4000m)
limits_mem   = fixed_base (~4.9Gi)   + MAX_NOTEBOOKS × 16Gi    + analysis (8Gi)
```

Tiers multiply the per-notebook values linearly (2x tier → ×2, 4x → ×4). Size the quota for the worst case: `MAX_NOTEBOOKS` all at 4x.

### With `MAX_NOTEBOOKS = 1` (default)

| | Requests | Limits (1x tier) | Limits (4x tier — quota target) |
|---|---|---|---|
| CPU | ~1880m | ~14650m | ~41650m |
| Memory | ~4Gi | ~29Gi | ~77Gi |

**Namespace limits quota must be ≥ sum of all container limits at full load.** If smaller, users hit 403 errors even when individual pods are within their own limits.

Set `resources.namespaceQuota.*` in `config.yaml` (or `config.dev.yaml`) to values ≥ the 4x tier column, rounded up to your node size.

---

## Setting quotas in Rancher

1. Edit `resources.namespaceQuota.*` in `config.yaml`.
2. Run `make deploy` — renders values into the hub's `extraEnv`; the pre-spawn hook applies them when creating user namespaces.
3. **Existing namespaces** are only updated on next login. To force an immediate update, patch the namespace annotation manually or delete the namespace.

### Using `make resources`

```
make resources  # uses ENV=dev
make resources ENV=prod
```

Prints per-component breakdown, formula minimums, and a comparison against the configured quota values. Run this before setting Rancher quotas.

---

## Notebook resource tiers

Users choose between **1x**, **2x**, and **4x** tiers when starting a notebook. The API multiplies all CPU and memory values in `resources.notebook` by the tier factor at runtime — no per-tier config needed. An optional **GPU toggle** attaches a single GPU (`gpuType` config key → `GPU_TYPE` env var, e.g. `nvidia.com/mig-1g.10gb`) to the gmx container, independent of tier. GPU resources use a separate Kubernetes resource name and do not count toward CPU/memory quota.

### Pod labels

```yaml
labels:
  type: notebook
  tier: "2x"
  gpu: "false"
```

### Database columns

The `notebooks` table has `tier` (enum: 1x, 2x, 4x) and `gpu` (boolean) columns.

### API endpoints

- `POST /api/.../notebook` — accepts optional `{"tier": "2x", "gpu": true}` JSON body
- `GET /api/.../notebook-config` — returns available tiers and the default tier
