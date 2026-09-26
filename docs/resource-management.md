# Resource Management

## Namespace structure

Each user gets an isolated Kubernetes namespace (`{helm-package}-user-{username}-ns`) managed by JupyterHub's pre-spawn hook. Two categories of workload run there:

> `{username}` is normalized to a Kubernetes DNS-1123-safe slug, so OIDC usernames containing dots or other invalid characters (e.g. `john.doe` → `john-doe`) do not break namespace creation. The raw username is still used for JupyterHub routing.

| Category | Lifetime | Examples |
|---|---|---|
| Always-on | While the user is logged in | JupyterHub singleuser pod + sidecars (proxy, auth, api, s3sync) |
| On-demand | User-initiated, short to long-lived | Notebook pods, analysis jobs |

The hub namespaces — `md-dashboard-ns` (prod) and `mddash-dev` (dev) — host JupyterHub itself, mdrun-api, Tuner, and the landing page; those are not covered by per-user quotas. Both live in the same Rancher project, so the project limit must cover both hubs plus all user namespaces.

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

**Fixed overhead total:** ~280m CPU / ~760Mi memory (requests) · ~1650m CPU / ~4.6Gi (limits)

---

## On-demand workloads

### Notebook pods

Resources are configured via `resources.notebook` in `config.yaml`. The notebook pod is a single `jupyter` container; GROMACS and AmberTools binaries are bundled in the notebook image.

| Container | CPU req | Mem req | CPU lim | Mem lim |
|---|---|---|---|---|
| jupyter | 500m | 1Gi | 5000m | 8Gi |

**Why jupyter limits are generous:** GROMACS runs with MPI/OpenMP inside the notebook container, where CPU throttling causes rank starvation and incorrect simulation results, and notebooks can spike in memory (e.g. loading a large trajectory). The 8Gi limit prevents a runaway computation from OOMKilling other pods.

`resources.notebookQuota.maxConcurrent` sets the API-enforced count limit on concurrent notebook pods (passed to the API as `NS_MAX_NOTEBOOKS`, a **required** env var — the API refuses to start without it and exposes it via `GET /api/.../notebook-config` as `concurrentLimit`). It is sized so that `maxConcurrent` notebooks at the **4x tier** fit within the namespace quota — the same quota headroom fits `maxConcurrent × 4` notebooks at 1x tier.

### Analysis jobs

| | CPU | Memory |
|---|---|---|
| Request | 1000m | 2Gi |
| Limit | 1000m | 8Gi |

Batch jobs (mddb_wf). Only one analysis job per experiment can be active at a time (enforced by job naming).

---

## Quota formula

```
# user_pod = sidecars + singleuser = 280m CPU / 760Mi mem (requests), 1650m CPU / 4.6Gi mem (limits)
requests_cpu = user_pod (280m)   + MAX_NOTEBOOKS × tier×500m   + analysis (1000m) + upload (100m)
requests_mem = user_pod (760Mi)  + MAX_NOTEBOOKS × tier×1Gi    + analysis (2Gi)   + upload (128Mi)
limits_cpu   = user_pod (1650m)  + MAX_NOTEBOOKS × tier×5000m  + analysis (1000m) + upload (500m)
limits_mem   = user_pod (4.6Gi)  + MAX_NOTEBOOKS × tier×8Gi    + analysis (8Gi)   + upload (256Mi)
```

Tiers multiply the per-notebook values linearly (2x tier → ×2, 4x → ×4). Size the quota for the worst case: `MAX_NOTEBOOKS` all at 4x.

### With `MAX_NOTEBOOKS = 2` (default)

| | Requests (worst case) | Limits (worst case) |
|---|---|---|
| CPU | ~5380m | ~43150m |
| Memory | ~10.9Gi | ~76.9Gi |

**Namespace limits quota must be ≥ sum of all container limits at full load.** If smaller, users hit 403 errors even when individual pods are within their own limits.

Set `resources.namespaceQuota.*` in `config.yaml` (or `config.dev.yaml`) to values ≥ the 4x tier column, rounded up to your node size.

---

## Setting quotas in Rancher

### Hub namespace quota

Rancher project limits are shared between both hub namespaces and every user namespace. The user namespace quotas are set automatically by MDDash from `resources.namespaceQuota.*` in `config.yaml`. Hub namespace quotas are set by `install.sh` from the `make resources` totals (or manually in the Rancher UI): prod caps `md-dashboard-ns`, dev caps `mddash-dev`.

To adjust a hub quota manually in Rancher, open **Cluster → Projects/Namespaces**, select the project, find the hub namespace, click **⋮ → Edit Config**, and set its Resource Quota to the `make resources` hub totals. The project limit minus the hub quotas must leave enough room for the planned number of user namespaces at full load.

1. Edit `resources.namespaceQuota.*` in `config.yaml`.
2. Run `make deploy` — renders values into the hub's `extraEnv`; the pre-spawn hook applies them when creating user namespaces.
3. **Existing namespaces** are only updated on next login. To force an immediate update, patch the namespace annotation manually or delete the namespace.

### Using `make resources`

```
make resources  # uses config.yaml
make resources ENV=dev  # uses config.dev.yaml
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
- `GET /api/.../notebook-config` — returns available tiers, the default tier, and `concurrentLimit` (max concurrent notebook pods per user)
