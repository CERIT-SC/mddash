# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

Read `AGENTS.md` (repo root) for the authoritative architecture and cross-component rules — it contains non-obvious contracts you must not break (error-handling contract duplicated across four services, S3 bisync rules, `.simulation.json` manifest pattern, Helm template flow). Component-specific rules live in nested `AGENTS.md` files (`dashboard/api/`, `dashboard/ui/`, `mdrun-api/`, `tuner/`, `hub/`, `landing/`, `notebook/`, `helm/charts/mddash/`, `.github/workflows/`); read the one for the component you're editing.

## Quality gates

Run from repo root, in this order, before claiming code is correct:

```bash
make fix              # auto-fix: Ruff format/check --fix + Prettier + Oxlint
make type-check       # ty (Python, per component via uv) + tsc (UI via pnpm)
make knip             # frontend dead code
make test             # pytest suites (dashboard/api, dashboard/auth, mdrun-api, tuner, pre_spawn_hook) + vitest
make e2e              # Playwright against the demo harness
make validate-charts  # REQUIRED when editing Helm charts/config (helm + gomplate + yq)
make lint-workflows   # REQUIRED when editing .github/workflows (actionlint + zizmor)
```

Running a single test:

```bash
cd dashboard/api && uv run pytest tests/test_foo.py::test_bar
cd dashboard/ui && pnpm vitest run path/to/file.test.tsx   # or: pnpm --filter dash test -- <pattern>
pnpm --filter @mddash/e2e test -- path/to.spec.ts
```

## Local development

- `make demo` — real Flask API (`dashboard/api/_demo/app.py`, mocked integrations, reseeded on every start) + React dev server at `http://localhost:5173/dash/` (ports 8888 / 5173).
- Tooling: `uv` (all Python), `pnpm` (all JS/TS). Use the VSCode dev container for the full toolchain (Docker-in-Docker, kubectl, helm).
- The `dashboard/ui` API client is **generated** from the Flask API's OpenAPI spec via orval: `pnpm run api:generate` regenerates it; CI enforces freshness (`pnpm run generated:check`). Never hand-edit generated output.

## Build / deploy

- `ENV=dev|prod` selects `config.${ENV}.yaml`; dev images are tagged `dev`, prod requires an explicit SemVer `IMAGE_TAG`.
- `make build ENV=dev` / `make deploy ENV=dev`; production releases only via `make release VERSION=x.y.z` (creates tag `v…`, `release.yml` deploys). `make all ENV=prod` is rejected by design.
- Never edit `helm/charts/mddash/values.yaml` — it is generated from `values.yaml.tmpl` by gomplate (`make -C helm render`).

## Big-picture architecture

Multi-tenant JupyterHub platform; each user gets a dedicated Kubernetes namespace whose pod runs sidecars next to the notebook, all sharing a PVC at `/mddash`:

- **Admin namespace**: `hub/` (custom JupyterHub image: k8s-hub + EGI authenticator + branded UI), `mdrun-api/` (executes GROMACS/AMBER K8s jobs independently of user sessions; SQLite WAL on a block PVC, status poller sidecar), `tuner/` (finds best MPI/OMP/GPU parameters), `landing/` (public page, optional in-cluster SeaweedFS S3).
- **User pod**: `dashboard/proxy/` (Caddy; single entry point, serves the compiled React UI from `dashboard/ui/`, routes via `forward_auth`), `dashboard/auth/` (validates JupyterHub OAuth sessions, in-memory 1h store), `dashboard/api/` (Flask business logic; Alembic migrations auto-applied on startup — add a migration for schema changes, no `db.create_all()` fallback), `dashboard/s3-sync/` (rclone bisync PVC↔S3).
- **Key invariants** (details in AGENTS.md): `.simulation.json` manifests are the single source of truth for simulation file roles; all four services share an identical RFC 9457 error contract in their `errors.py` (change one = change all four); exception text never leaks to clients; the dashboard API's Tuner and MDRepo clients are the *only* integration points for those services.

## CI/CD

`master` push → `cd.yml` (CI + dev deploy). `v*` tag → `release.yml` (CI + prod deploy + GitHub Release). PRs run CI only.
