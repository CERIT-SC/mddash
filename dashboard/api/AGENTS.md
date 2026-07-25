# MDDash API

## Mission

Flask REST API that orchestrates molecular dynamics experiments across Kubernetes, manages MDRepo OAuth, and coordinates with external services (MDRun, Tuner). Runs as a sidecar in the user pod.

## Core Practices

- Business logic lives on SQLAlchemy models (e.g. `Experiment.from_pdb()`, `Experiment.publish()`).
- Use `@handle_exceptions()` on JSON route handlers; set `rollback=True` on routes that modify the DB. Success returns `jsonify(data)`; errors raise `HTTPException` which `@handle_exceptions` converts to `{detail: "..."}`. Redirect-only OAuth routes handle redirects directly (no decorator).
- MDRepo file uploads run as durable Kubernetes Jobs (`upload/submission.py`); credentials are passed to the worker via container environment variables in the Job manifest.

## Non-Obvious Gotchas

### Simulation Manifests (`.simulation.json`)
- **Single source of truth**: each manifest declares file roles (`topology`, `structure`, `trajectory` for GMX; `topology`, `coordinates`, `control`, `trajectory` for AMBER) and `extra_args`. Job models reference `simulation_path` — they no longer store file names.
- `list_simulation_files()` finds `*.simulation.json` anywhere under the experiment directory (not just `production/`).
- `get_simulation()` validates against the JSON Schema referenced by `$schema` (which must be a mddash schema URL — see `manifest_schema.py`); invalid simulations are returned with errors and can't be used by downstream steps.
- A simulation is locked when its file is read-only or when a tuner/production job references its `simulation_path`. `mark_simulation_readonly()` chmods the file `0444`.

### Migrations
- `create_app()` runs `flask_migrate.upgrade()` on startup (skipped at head), falling back to `db.create_all()`. Add a migration file in `migrations/versions/` when adding columns. Do NOT manually run `flask db upgrade`.

### Authentication
- MDRepo OAuth tokens live in the Flask session, NOT the database. Use `MDRepoTokenManager(session).get_valid_token()`; refresh is automatic with exponential backoff (3 retries).

### Kubernetes
- **Lazy in-cluster config**: `config.load_incluster_config()` and client construction are deferred until first use — importing `clients.k8s` does NOT trigger K8s init. Tests must call `reset_k8s_clients_for_tests()` to clear cached clients between assertions.
- Jobs have `backoffLimit: 0` (no retries on failure).

### File Operations
- Git clones are shallow (`--depth 1`) with `.git` removed. Always validate paths with `check_path()`/`check_filename()` to prevent traversal. `is_excluded_path()` filters MDRepo uploads.
- Binder support: cloned repos may carry `environment.yml`/`requirements.txt`/`postBuild`; the notebook startup hook installs them at `/mddash/{experiment_id}/.binder-env`.

### Local Demo
- `dashboard/api/_demo/app.py` runs the real API with mocks applied before app import — this ordering matters; seeding/mocks live in `_demo/profile.py`.
