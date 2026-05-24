# Dashboard Startup Optimization Design

## Summary

Reduce the time from dashboard user pod container start to the first successful dashboard API/auth health response. The first pass focuses on measurement and low-risk startup trimming for the dashboard `api` and `auth` sidecars, plus health-check access-log cleanup where probe noise hides useful logs. It does not redesign JupyterHub spawning, namespace provisioning, S3 persistence, or the sidecar architecture.

## Current Context

Dashboard user pods are assembled by `helm/charts/mddash/files/pre_spawn_hook.py`. The pod contains the JupyterHub singleuser container plus sidecars for proxy, auth, API, and S3 sync. The API and auth containers are injected as extra containers with fixed resources:

| Container | CPU request | CPU limit | Memory request | Memory limit |
|---|---:|---:|---:|---:|
| auth | 10m | 100m | 48Mi | 96Mi |
| api | 50m | 250m | 128Mi | 512Mi |

The dashboard API currently does several things before it can serve a health response:

- imports all route modules from `dashboard/api/routes/__init__.py`
- imports the Kubernetes client path via `routes/misc.py` -> `clients.k8s`
- calls `config.load_incluster_config()` and constructs Kubernetes API clients at `clients/k8s.py` import time
- runs Alembic migration handling in `create_app()`
- starts the storage-size monitor, which immediately runs `du -sb /mddash` in a background thread
- constructs the app at module import with `app = create_app()` while production Gunicorn also uses `app:create_app()`

The proxy waits for `http://localhost:5001` and `http://localhost:5000`, but it does not use `curl --fail` and does not target `/health`, so a non-2xx HTTP response can satisfy the wait. Dockerfile `HEALTHCHECK` directives are not Kubernetes readiness probes for these injected sidecars.

The `mdrun-api` service is separate from the dashboard user pod, but its health endpoint is currently noisy in logs. Industry practice is to suppress routine successful probe access logs while preserving failed probes, application errors, and useful startup/diagnostic logs.

## Goals

- Measure startup phases clearly enough to distinguish CPU-bound Python startup, PVC/SQLite migration work, Kubernetes client setup, proxy waiting, and auth startup.
- Reduce API first-health latency without weakening schema safety.
- Keep auth behavior unchanged unless measurement shows it is a meaningful contributor.
- Make proxy startup wait for real health success instead of any HTTP response.
- Suppress successful health-check access-log noise, especially for `mdrun-api`, without hiding failures.
- Preserve existing sidecar topology and user-facing dashboard behavior.

## Non-Goals

- Redesign JupyterHub spawning or Rancher namespace provisioning.
- Move dashboard API out of the user pod.
- Replace SQLite or Alembic.
- Redesign S3 sync semantics.
- Optimize total spawn time from login/click to dashboard page load beyond what directly affects dashboard health.
- Change `mdrun-api` request handling or health response semantics beyond access-log filtering.

## Proposed Approach

Use an instrumentation-first, low-risk trimming approach.

1. Add startup timing logs around API and auth phases.
2. Remove avoidable duplicate API app construction.
3. Keep migrations startup-gated when needed, but skip full Alembic `upgrade()` when the database is already at the script head.
4. Lazy-load Kubernetes clients so the health route does not initialize in-cluster Kubernetes access.
5. Defer the initial `/mddash` storage-size scan until after first health or first `/metrics` use.
6. Make proxy wait for explicit health endpoints with successful status codes.
7. Suppress successful health endpoint access logs at the server/logging layer, starting with `mdrun-api`.

This approach should provide useful before/after evidence and reduce first-health latency while avoiding a larger lifecycle redesign.

## Architecture

### Startup Timing

The API should emit structured, timestamped startup logs for these phases:

| Phase | Purpose |
|---|---|
| process/import start | Measures Python import and module-level work. |
| Flask app factory start/end | Measures app construction cost. |
| DB revision check start/end | Measures SQLite/PVC metadata work. |
| migration upgrade start/end | Measures actual schema changes when needed. |
| route registration done | Confirms app routing is ready. |
| background monitor scheduled | Confirms nonessential IO is no longer blocking health. |
| first health request | Confirms first externally observable readiness. |

Auth should emit a smaller set of timing logs: module import/app creation complete and first `/health` request.

The logging should use the existing Python logging configuration. Instrumentation must not prevent startup if logging configuration is incomplete.

### API App Construction

The production API container uses Gunicorn with `app:create_app()`. The module-level `app = create_app()` causes avoidable app construction during module import. The design is to use a single application creation path for production. Direct `python app.py` development usage can still create the app inside the `__main__` branch.

### Database Migration Handling

Schema safety remains startup-gated. If the database is unversioned, unknown, or behind head, startup still performs the existing migration/stamp handling before serving the API.

When the database revision is already equal to the Alembic script head, the API should skip `upgrade()`. This avoids invoking full migration machinery on every user pod start while preserving correctness for real migrations.

Migration fallback to `db.create_all()` can remain for the first pass, but logs should clearly show when fallback happens because it may hide migration defects.

### Kubernetes Client Loading

The health endpoint should not require Kubernetes client initialization. `clients.k8s` should expose cached helper functions that load in-cluster config and construct `CoreV1Api`/`BatchV1Api` only when a route actually needs Kubernetes.

Routes that need Kubernetes keep using the client module through the same public operations. Internals can change from module-level clients to lazy cached clients without changing API route behavior.

### Storage Size Monitor

The storage-size monitor should not compete with first health. Two acceptable implementations are:

- schedule the monitor thread with an initial delay, or
- compute storage size lazily on first `/metrics` request and then continue periodic updates.

The simpler first pass is an initial delay. It keeps `/metrics` behavior eventually consistent and avoids introducing request-time `du` latency.

### Proxy Health Wait

The proxy command should wait for explicit endpoints:

- `http://localhost:5001/health` for auth
- the dashboard API health endpoint for API

Because the API route prefix includes `JUPYTERHUB_SERVICE_PREFIX`, the proxy command should use the same route prefix it already receives through `CADDY_ROUTE_PREFIX`, for example `http://localhost:5000${CADDY_ROUTE_PREFIX}/dash/api/health`.

The wait should use `curl --fail` so only successful HTTP status codes pass. The retry interval can remain short, but logs should make prolonged waits diagnosable.

### Health Access Logging

Routine successful health/readiness probe requests should not congest access logs. The first target is `mdrun-api`, where `/api/health` is checked frequently by Kubernetes probes and generates low-value noise. The preferred implementation is server-level filtering in the `mdrun-api` uWSGI startup/configuration so successful `GET /api/health` access lines are suppressed before they reach stdout.

The filtering policy should be narrow:

- suppress successful health endpoint access lines only
- keep failed health probes visible
- keep application errors and stack traces visible
- keep startup timing and migration/DB diagnostic logs visible
- avoid adding health-path conditionals to Flask business route code unless the server cannot express the filter cleanly

Dashboard API/auth can adopt the same policy later if their successful probe logs become noisy, but they are secondary to `mdrun-api` for this pass.

## Data Flow

Startup after the change:

1. Kubernetes starts auth and API sidecars.
2. Auth imports quickly and serves `/health`.
3. API imports modules without constructing the Flask app twice.
4. API creates the Flask app once.
5. API checks the database revision.
6. API skips migration upgrade if the DB is already at head, or applies migrations if needed.
7. API schedules nonessential storage scanning after the first-health critical path.
8. API serves the dashboard health endpoint.
9. Proxy starts Caddy only after auth and API health endpoints return successful status codes.
10. Routine successful probe traffic is omitted from high-volume access logs, while failures remain diagnosable.

## Error Handling

- Timing logs must be best-effort and never fatal.
- Migration errors keep the current fallback behavior for the first pass, with clearer warning logs.
- Lazy Kubernetes client initialization errors should surface only on endpoints that need Kubernetes, not on `/health`.
- Proxy health waiting should fail visibly through container logs if auth or API never becomes healthy.
- Health access-log filtering must not suppress failed probes, exceptions, or non-health requests.

## Testing And Verification

### Automated Tests

- API migration tests:
  - DB already at Alembic head skips `upgrade()`.
  - DB behind head still runs upgrade.
  - unversioned DB with tables preserves the baseline stamping behavior.
- API import/health test:
  - health route can be imported and served without constructing Kubernetes clients.
- Auth health test:
  - `/health` returns `200 OK` under required environment variables, if existing coverage is insufficient.
- Health access-log filtering test or configuration verification:
  - successful `mdrun-api` `/api/health` probes are not emitted as routine access logs
  - failed health probes or application errors remain visible

### Manual Cluster Verification

Collect before/after evidence from a user pod startup:

- Kubernetes pod events for image pull and container start timing.
- API logs showing startup phase durations.
- Auth logs showing first health timing.
- Proxy logs showing how long it waited for auth/API health.
- First successful dashboard API health response time from inside the pod.
- `mdrun-api` logs showing that routine successful `/api/health` probe noise is absent while non-health requests and errors remain visible.

Success means the logs can explain where startup time is spent and the API first-health path no longer performs duplicate app construction, unnecessary migration upgrade calls when already current, eager Kubernetes client setup, or immediate storage scanning. Success also means routine successful health probe logs no longer drown out operationally useful `mdrun-api` logs.

## Rollout

1. Implement instrumentation and low-risk API/auth/proxy changes in dev.
2. Compare dev pod startup logs before and after.
3. If API health latency remains high, use the timing logs to decide whether resource tuning, image pull optimization, or lifecycle splitting is the next bottleneck.
4. Promote to production only after dev startup behavior and health checks are stable.

## Risks And Mitigations

| Risk | Mitigation |
|---|---|
| Skipping `upgrade()` misses a needed migration. | Skip only when current revision exactly equals Alembic script head. |
| Lazy Kubernetes clients change route behavior. | Keep public client operations stable and test health import separately. |
| Proxy health URL is wrong because of route prefix handling. | Build the URL from `CADDY_ROUTE_PREFIX` and verify in a spawned dev pod. |
| Delaying `du` makes `/metrics` storage temporarily unknown. | Existing `get_du_size()` already supports `None`; keep that behavior. |
| Startup logs become noisy. | Use concise INFO logs for phase duration and warnings only for abnormal paths. |
| Health log filtering hides real failures. | Filter only successful health access lines and verify failures/errors still appear. |

## Open Decisions

No open product decisions remain for the first pass. If measurements show cluster resource throttling dominates after low-risk trimming, resource tuning should be handled as a follow-up design or a small separate change.
