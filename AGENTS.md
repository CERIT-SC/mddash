# MDDash - Molecular Dynamics Dashboard

## Mission

Multi-tenant JupyterHub-based platform for molecular dynamics simulations. Orchestrates GROMACS and AMBER jobs, provides wizard-driven experiment workflows, and integrates with external services (MDRepo, S3, Gromacs Tuner) through isolated per-user Kubernetes namespaces with sidecar containers.

## Architecture

Each user gets a dedicated Kubernetes namespace with resource quotas managed via Rancher project annotations. JupyterHub spawns an isolated user pod containing sidecar containers alongside the notebook:

```
Admin namespace:  JupyterHub Hub, MDRun API, Gromacs Tuner, Landing Page (Caddy)
User namespace:   Proxy (Caddy) -> Auth (Flask), API (Flask), S3-Sync (rclone), JupyterHub Singleuser
External:         MDRepo, S3-compatible storage
```

The Proxy container serves the complete static UI (compiled React/TypeScript dashboard) embedded as static assets in its image, and routes to the JupyterHub Singleuser service configured in `values.yaml.tmpl`.

## Core Patterns

- **Simulation Manifest Pattern**: `.simulation.json` files are the single source of truth for file roles and `extra_args`. Job models reference `simulation_path` instead of storing file names. (Dashboard API + UI)
- **Sidecar Polling Pattern**: MDRun API's poller sidecar co-locates with the API on one PVC and polls K8s job status on an interval — SQLite on a block-device-backed volume, never NFS (WAL is unsupported on network filesystems).
- **Template-Based Configuration**: `helm/charts/mddash/values.yaml.tmpl` is rendered with `gomplate` before Helm. Never edit `values.yaml` — it's generated.

## Cross-Component Gotchas

### Configuration
- **Environment = explicit `ENV`**: `ENV=dev` or `ENV=prod`, defaulting to `dev`. Dev images use a static `dev` tag; prod uses immutable SemVer tags (e.g. `0.1.0`) provided by the release workflow. No branch-based inference.
- **Runtime config injection**: UI receives config via `window.MDDASH_CONFIG` injected by Caddy at `{$CADDY_ROUTE_PREFIX}/dash/config.js`. Dev mode is detected when this is undefined.

### Authentication
- All auth flows through JupyterHub OAuth2.
- Auth service uses an in-memory session store (1-hour lifetime) with HMAC-signed state.
- Caddy `forward_auth` validates sessions via the auth container before routing to API or UI.
- MDRepo OAuth is a separate flow managed by Dashboard API; tokens live in the Flask session (not the database).

### Kubernetes
- Dashboard API, MDRun API, and pre_spawn_hook all use `config.load_incluster_config()`. The hub pod's service account needs the ClusterRole in `helm/rbac/` applied by the cluster admin.
- All containers run as non-root (UID 1000) for e-INFRA compliance.
- All user-pod containers mount a shared PVC at `/mddash`.
- User namespaces require `field.cattle.io/projectId` and `field.cattle.io/resourceQuota` annotations. The pre-spawn hook waits for `InitialRolesPopulated`, patches the namespace, then waits for ResourceQuota to become active.

### S3 Sync
- The user-pod sidecar (`dashboard/s3-sync/`) runs `rclone bisync` between `/mddash` (PVC) and S3. bisync state (`--workdir /mddash/.rclone-bisync`) MUST live on the PVC — if it's ephemeral, restarts force `--resync`, which only copies and re-creates files/dirs deleted on the other side.
- `--resync` runs ONLY on a genuine first run (empty workdir) or as last-resort recovery; normal runs use `--recover --resilient --max-lock 2m`. Every `--resync` invocation MUST also pass `--max-lock`: a lock's expiry is set by the process that creates it, so an interrupted resync without `--max-lock` leaves a never-expiring `.lck` that blocks all future runs (the normal loop's `--max-lock` can't break a lock it didn't create).
- A `.s3-init` marker file (non-excluded) keeps both paths non-empty so bisync's empty-path safety check doesn't abort every cycle on a fresh PVC.
- Do NOT add `--create-empty-src-dirs`: S3 can't durably hold truly-empty dirs, so the flag records a phantom dir on S3 and the next cycle deletes it from the PVC (symptom: empty dirs vanish). Without it, empty dirs are left untouched on each side (never deleted, not propagated to S3).
- The image pins `rclone/rclone:1.74.4` via multi-stage (alpine's `apk` package ships a stale `-DEV` build).

### Database
- **Dashboard API**: runs `flask_migrate.upgrade()` on startup against versioned migrations in `dashboard/api/migrations/versions/`. Falls back to `db.create_all()` if migration fails. Add a new migration file when adding columns — do NOT manually run `flask db upgrade`.
- **MDRun API**: `db.create_all()` only — no Alembic migrations. SQLite WAL mode for concurrent reads/writes.

### Error Handling
- Dashboard API routes return raw resources via `jsonify()` on success and raise `HTTPException` (`BadRequest`, `NotFound`, …) for errors. `@handle_exceptions` catches them and returns `{detail: "..."}` with the correct status code.
- Use `@handle_exceptions()` on JSON route handlers; set `rollback=True` on routes that modify the database.
- Missing env vars log warnings but don't crash (graceful degradation).

## Development & Feedback Loop

- `make demo` runs the real Flask API (`dashboard/api/_demo/app.py`, test-style mocks + seeded data) plus the React dev server locally.
- Run from repo root before claiming any code is correct — each must pass before the next:

```bash
make fix
make type-check
make test
make lint-helm-fast
make lint-workflows
```

- Build/deploy: `make build ENV={dev,prod}`, `make deploy ENV={dev,prod}`, `make rollback ENV=prod REVISION=N`.
- Production application releases use SemVer tags (`v0.1.0`). `make all ENV=prod` is rejected — operators only need `ENV=prod` for `status`/`logs`/`history`/`rollback`.
- Helm: `make -C helm render` (render values), `make -C helm update` (update deps).

## CI/CD

- `ci.yml`: lint, test, type-check, Helm validation, and workflow validation (actionlint + zizmor) on every PR and `master` push. Supports `workflow_call` so `release.yml` can reuse it as a release quality gate.
- `deploy-dev.yml`: triggered by a successful `CI` `workflow_run` for a `master` push. Verifies the run was a successful push from this repository, then deploys all images as `dev` to the dev environment via `_deploy.yml`.
- `release.yml`: triggered by `v*` tags. Validates strict SemVer and `master` ancestry, calls `ci.yml` as a quality gate, then deploys immutable images and Helm charts to prod via `_deploy.yml`, verifies health, and creates a GitHub Release.
- `_deploy.yml`: reusable workflow owning build matrices, OCI labels, BuildKit cache, Helm deployment (atomic + wait), health verification, and failure diagnostics. Called by both `deploy-dev.yml` and `release.yml`.
- `codeql.yml`: CodeQL for Actions, JS/TS, Python on `master` pushes/PRs + weekly.
- Tools (yq, gomplate, actionlint, zizmor) are installed from pinned release versions via inline `curl` (yq, gomplate) and `pip` (zizmor). All Actions are pinned to full commit SHAs with version comments. Dependabot updates Actions monthly.
- Secrets are created in-namespace during deployment via GitHub Actions.
