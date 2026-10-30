# Per-user usage monitoring - design

- Issue: [CERIT-SC/mddash#169](https://github.com/CERIT-SC/mddash/issues/169): *"Add some monitoring so we can see usage by individual users."* MDRun first (most expensive), optionally paired with Grafana; Tuner and user namespaces are nice-to-have.
- Status is Approved (2026-10-27).
- Scope is operator-facing usage attribution and dashboards. Per-user quotas, billing, user-facing usage views, alerting, and log aggregation are out of scope.

## Summary

Today nothing can answer "who used what". MDRun and Tuner jobs run in the hub namespace and record no owner, start, end, or resources, and a simulation's MDRun row is deleted when it is re-run. Platform metrics do not fill the gap. The tenant offering (Personal Monitoring) reports namespace/pod requests and usage only, keeps 14 days, has no persistent storage, and cannot tell MDDash users apart inside the hub namespace.

The services therefore record usage themselves, and Grafana reads it:

1. **Usage ledger (MDRun).** An append-only `mdrun_usage` table records owner, requested resources, and allocation start/end per job, and is never deleted. `make usage` prints per-user CPU-hours, GPU-hours, and estimated cost for any period.
2. **Prometheus + Grafana** (opt-in, `monitoring.enabled`), as subcharts in the hub namespace. Services export ledger-derived counters on a dedicated port, Grafana ships a provisioned "Usage by user" dashboard, and access is via `kubectl port-forward`.
3. **Tuner ledger**, with the same shape per trial.
4. **User namespaces** (notebooks, GPU notebooks, analysis) via CERIT's `project-stats` exporter, if the phase 0 spike shows it covers the whole Rancher project.

Each phase ships on its own. Phase 1 alone answers the issue's primary ask.

## Background facts

| Fact | Consequence |
|---|---|
| MDRun Jobs run in the hub namespace as `mdrun-{uuid}`, and their labels carry no user. `mdrun_jobs` stores only `id`, `job_name`, `experiment_id`, `created_at`, `last_status`. | Namespace-level metrics cannot attribute MDRun usage. MDRun must record the owner. |
| The dashboard API knows the user: `JUPYTERHUB_USER`, and `POD_NAMESPACE` = `{package}-user-{slug}-ns` (set by the pre-spawn hook). Today MDRun receives only the per-user `bucket_name`. | Pass the owner explicitly. The namespace name is a stable, label-safe key that joins with namespace metrics. |
| `RunService.replace_terminal_run`/`remove` call MDRun `DELETE`, which deletes the `mdrun_jobs` row, so every re-run erases the previous record. Tuner `DELETE` cascades job and trial rows. | Usage cannot live on job rows. It needs its own never-deleted table. |
| MDRun uses `db.create_all()` without Alembic. `create_all` creates missing tables but never alters existing ones. | A new table needs no migration tooling. New `mdrun_jobs` columns would. |
| The poller runs every 900 s. Terminal K8s Jobs are deleted on detection, with a 3600 s TTL as backstop. | Read start/end from pod status at the transition, not from observation time. |
| MDRun is unauthenticated, and no MDDash NetworkPolicy restricts its callers. Tuner shares one Basic Auth credential (`tuner/AGENTS.md`). | `owner` is a client claim. It is accurate on the dashboard path but forgeable by direct callers until per-user authentication exists, which is a separate issue. |
| Tuner prices resources already (`tuner.api.pricing`: CPU-core-hour, GPU-hour, GB-RAM-hour; `ResourceFootprint.hourly_cost()`). | One set of rates serves all cost estimates. |
| Every hub-namespace pod must declare requests and limits (Rancher ResourceQuota) and be listed in `scripts/resource_summary.py`. SQLite and Prometheus TSDB need block storage (`csi-ceph-rbd-du`), never NFS. | These constrain the monitoring subcharts. |
| The chart already ships a condition-gated third-party subchart (SeaweedFS). Tuner already relies on a NetworkPolicy to isolate Ray. | Use the same patterns for Prometheus/Grafana and for restricting the metrics port. |
| e-INFRA *Personal Monitoring* (Rancher app, chart `cerit-sc/monitoring-personal`) runs a Prometheus without a PV (14 d retention) that scrapes only CERIT's `project-stats` exporter: `container_resource_{request,limit,usage}{namespace,pod,container,resource}` (incl. `nvidia_com_gpu`) and `namespace_quota`. A namespace can hold at most one instance, with Grafana at `pmon-<ns>.dyn.cloud.e-infra.cz`. It has no pod labels, no GPU utilization, and a fixed scrape config. | Good for a quick namespace-level look. It cannot attribute MDRun or hold accounting history. Its exporter may serve phase 4. |
| CERIT's chart repo includes `pod-banking` (pod metrics into InfluxDB, cluster-scoped RBAC). | CERIT may already record per-namespace usage. Ask before building phase 4. |

## Options

### Source of usage data

| Option | Pros | Cons |
|---|---|---|
| **A. Service-level ledger (recommended)** | Exact owner attribution. Durable on the existing block PVC. Independent of platform monitoring. Reports cover any period. | Allocation-based (requested × wall time), not measured utilization. Owner is client-asserted. |
| B. Cluster metrics + pod labels | Measured CPU/memory utilization. | Tenant access to kubelet/kube-state-metrics is unlikely (phase 0 confirms). `project-stats` drops pod labels. Retention is too short for accounting. Still needs an owner join metric. |
| C. Run MDRun Jobs in the user's namespace | Attribution and per-user quotas come from the namespace. | Cross-cutting redesign: MDRun RBAC and S3 credentials per namespace, quota sizing for 16-CPU/GPU jobs. Still needs durable history. Warrants its own design if per-user fairness becomes a goal. |

Allocation is the right basis for cost: a reserved GPU is unavailable to others whether or not the job saturates it.

### Presentation

| Option | Pros | Cons |
|---|---|---|
| **G1. Own Prometheus + Grafana subcharts (recommended)** | Scrapes our exporters. Persistent. Dashboards versioned in the repo. Deployed by `make deploy`. | Two more hub pods to size and upgrade. |
| G2. CERIT Personal Monitoring | No code; one Rancher install. | Cannot scrape our metrics. No persistence, 14 d retention, installed by hand outside Helm. |
| G3. Report only (`make usage`) | Smallest. Exact. | No trends or live view. |

G3 ships in phase 1 regardless, and G1 builds on it in phase 2. G2 serves only as phase 0 tooling.

### Grafana access

| Option | Notes |
|---|---|
| **`kubectl port-forward` (recommended first)** | `make grafana ENV=…`. Kubernetes RBAC is the gate. Grafana uses anonymous Viewer, with no secrets and no ingress. |
| Ingress + e-INFRA OIDC | A `*.dyn.cloud.e-infra.cz` host with cert-manager. Needs an OIDC client and a user allowlist. Add it when people without kubectl need access. |
| Ingress + JupyterHub as OAuth provider | Reuses hub login, gated on hub admin. MDDash configures no hub admins today. |

## Design

### Usage semantics

- A billable unit is one MDRun job (phase 1) or one Tuner trial (phase 3).
- The allocation window runs from pod `status.startTime` (resources bound, including image pull and S3 download) to the latest container `finishedAt`. Fallbacks:
  - observation time at the transition;
  - `stop()`/`DELETE` close at request time;
  - a job that disappears from Kubernetes while non-terminal closes when first seen missing (error ≤ one poll interval).
- Usage is requested CPU cores, memory GiB, and GPUs × window. Reports clip windows to the requested period, so a job that spans two months splits correctly.
- Cost is usage × the `tuner.api.pricing` rates, shown as an estimate.
- Jobs created before the deploy have no ledger row, and the write points skip them. There is no backfill.

### Attribution contract (dashboard API → MDRun, Tuner)

- Create requests gain optional `owner` (JupyterHub username) and `owner_namespace` (`POD_NAMESPACE`). They are optional so that user pods still on the old dashboard image keep working. Missing fields record as unattributed.
- `owner_namespace` becomes a label value, so `sanitization.py` validates it as a DNS-1123 label and returns a 400 problem-details otherwise.
- The MDRun Job and pod template get labels `mddash.io/user-namespace`, `mddash.io/workload: mdrun`, and `mddash.io/engine`. They also get the annotation `mddash.io/user`, because raw usernames are not always valid label values. Operators can see whose pods hold GPUs right now (`kubectl get pods -L mddash.io/user-namespace`).

### MDRun ledger (phase 1)

`mdrun_usage` is created by `create_all` and its rows are never deleted. Columns: `job_id` (PK), `engine`, `owner`, `owner_namespace`, `experiment_id`, `cpu_cores`, `memory_gib`, `gpus`, `created_at`, `started_at`, `finished_at`, `outcome`.

The resource helpers return numbers that feed both the manifest and the ledger, so the two cannot drift. Write points (`models.py`, `routes.py`):

| Event | Ledger update |
|---|---|
| POST create | Insert with requested resources. |
| Transition to RUNNING | `started_at` from pod `startTime`, if unset. |
| Transition to FINISHED/ERROR (before the K8s delete) | `started_at` if unset, `finished_at` from the pod, `outcome`. |
| `stop()` | `finished_at = now`, `outcome = stopped`. |
| `DELETE` | Close if open with `outcome = deleted`. The job row is still deleted, as today. |
| K8s `NOT_FOUND` while non-terminal | Close at now with `outcome = unknown`. |

Status reads run concurrently, because the dashboard polls the experiment and the run endpoints together and MDRun serves them in parallel. Every path that deletes the Job (finish, stop, `DELETE`) closes the window first, and every ledger write is a conditional `UPDATE` that only fills unset fields. A read that finds the Job already gone then waits on SQLite's write lock and changes nothing, so it can't relabel a finished run as `unknown`.

The report is `python -m usage --since … [--until …] [--csv]`, run inside the mdrun-api image by `make usage ENV=… SINCE=… UNTIL=…` through `kubectl exec`. It adds no new network surface. Columns: user, namespace, jobs, CPU core-h, GPU-h, memory GiB-h, estimated cost.

### Metrics exporter (phase 2)

- The poller container serves `/metrics` on port 9100 with `prometheus_client`. A custom collector queries the ledger at scrape time, so counters survive restarts and gunicorn multiprocess mode is unnecessary.
- A NetworkPolicy keeps port 5000 open as today and admits 9100 only from the Prometheus pod. Usernames do not leave the hub namespace.
- Series carry the labels `user`, `namespace`, and `engine`. Cardinality is tens of users.
  - Counters: `mddash_mdrun_jobs_started_total`, `mddash_mdrun_cpu_core_seconds_total`, `mddash_mdrun_gpu_seconds_total`, `mddash_mdrun_memory_gib_seconds_total`.
  - Gauges: `mddash_mdrun_allocated_cpu_cores`, `mddash_mdrun_allocated_gpus`.

### Monitoring stack (phase 2)

- `monitoring.enabled` in `config*.yaml` gates two subcharts. Enable on dev first.
  - `prometheus-community/prometheus`: server only (no Alertmanager, kube-state-metrics, node-exporter, pushgateway, or configmap-reload), `rbac.create: false`, static scrape targets.
  - `grafana/grafana`: no RBAC, no dashboard sidecar, no init-chown.
- Prometheus TSDB lives on a `csi-ceph-rbd-du` PVC, with ~13 months of retention. At this cardinality it stays small.
- Grafana is stateless. Its datasource and dashboards are provisioned from `helm/charts/mddash/dashboards/*.json`. Anonymous Viewer with `viewers_can_edit` enables Explore.
- Every container gets the e-INFRA hardening (non-root, seccomp `RuntimeDefault`, drop `ALL`) and explicit resources, and is added to `scripts/resource_summary.py`.
- The "Usage by user" dashboard shows:
  - a per-user table for the selected range (`increase(…[$__range])`);
  - allocated GPUs and CPUs over time, stacked by user;
  - jobs started by engine.
- `make usage` keeps exact long-range accounting. Grafana ranges are bounded by Prometheus retention.

### Tuner (phase 3)

- The submit form gains `owner` and `owner_namespace`. The job thread writes one `tuner_usage` row per trial (Alembic migration `003`), and job `DELETE` never removes these rows.
- Trial timing:
  - `_run_single_trial` captures `started_at`/`finished_at` on the worker and returns them with its result.
  - Trials cancelled mid-run close at cancellation. Their start comes from the Ray State API task record that `trial_status_overrides` already queries; confirm the fields during implementation.
- The per-trial footprint comes from `ResourceFootprint` (cores, GPUs, RAM GiB), which already mirrors MDRun sizing.
- The worker's idle tail after the last trial (up to `idleTimeoutSeconds`, 1 h in prod) is platform overhead and stays unattributed. Phase 4 shows it as `tuner-raycluster-workers-*` usage.
- Tuner uses the same exporter pattern and port, and its panels join the usage dashboard.

### User namespaces (phase 4, gated on phase 0)

User namespaces are already per user, so attribution is free. If `project-stats` reports every namespace in the Rancher project, phase 4:

- deploys it in the hub namespace and scrapes it from our Prometheus;
- adds panels for per-namespace CPU/memory/GPU requests and usage (GPU notebooks, analysis jobs) and for Tuner worker overhead.

Otherwise, ask CERIT for `pod-banking` exports or kube-state-metrics access before building anything.

## Plan

| Phase | Size | Deliverables | Verification |
|---|---|---|---|
| 0. Platform spike (parallel, no code) | S | Check for `monitoring.coreos.com` CRDs. Install Personal Monitoring in `mddash-dev` and record which namespaces and GPU requests `project-stats` reports, then uninstall. Ask CERIT about reusing `project-stats` and about `pod-banking` data. | Findings recorded in this spec. Phase 4 go/no-go. |
| 1. MDRun ledger + report | M | Owner fields (dashboard MDRun client, gmx submit/extend, amber submit, demo fakes). Schema and sanitization. Labels. `mdrun_usage` model and write points. Pod-time helper in `k8s_client`. Pricing env on mdrun-api. `usage` CLI and `make usage`. Docs (`mdrun-api/AGENTS.md`, root `AGENTS.md`). | Unit tests for each write point, window clipping, unattributed rows, and old-client payloads. On dev, run a short job: `make usage ENV=dev` shows it, and `kubectl get pods -l mddash.io/workload=mdrun` shows the labels. |
| 2. Prometheus + Grafana | M | Exporter on the poller. NetworkPolicy. Subcharts behind `monitoring.enabled`. Dashboard JSON. `make grafana`. `resource_summary.py`. `docs/deployment.md`, `docs/resource-management.md`. | `make validate-charts`. On dev: Prometheus target up, and the dashboard matches `make usage` for the same range. |
| 3. Tuner ledger | S-M | Form fields, trial timing, migration, exporter, panels. | Unit and migration tests. `make -C tuner e2e ENV=dev` produces a job that appears in `make usage` and Grafana. |
| 4. Namespace usage | S | `project-stats` deployment, scrape config, panels. | A dev user namespace and the Tuner worker appear in Grafana. |

Every phase passes `make fix`, `make type-check`, `make knip`, `make test`, and `make e2e`.

## Open decisions

1. Ledger first (A, with G3 then G1), or Personal Monitoring (G2) only.
2. Grafana access: port-forward to start, or SSO ingress from day one.
3. Pricing: reuse `tuner.api.pricing` for MDRun estimates as is, or promote it to a top-level `pricing` key.
4. Retention of per-user usage data: keep the ledger indefinitely? Keep Prometheus for 13 months?
5. Trust model: accept a client-asserted `owner` now, and track per-user authentication for MDRun/Tuner as a separate security issue.

## Non-goals

- Per-user quotas or fairness scheduling.
- Billing.
- User-facing usage views.
- Alerting.
- Log aggregation.
- Measured utilization (cAdvisor, DCGM).
- Backfilling historical jobs.
