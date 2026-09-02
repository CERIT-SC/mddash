# MDDash API

## Mission

Flask REST API that orchestrates molecular dynamics experiments across Kubernetes, manages MDRepo OAuth, and coordinates with external services (MDRun, Tuner). Runs as a sidecar in the user pod.

## Core Practices

- Business logic lives on SQLAlchemy models (e.g. `Experiment.from_pdb()`, `Experiment.publish()`).
- Routes raise `HTTPException` subclasses or marshmallow `ValidationError` — the global `@app.errorhandler` handlers (in `errors.py`, registered via `register_error_handlers(app)`) convert them to RFC 9457 problem-details responses: `{"type": "urn:mddash:<token>", "title": "<Problem>", "detail": "<Cause>"[, "solution"]}`. No `@handle_exceptions` decorator needed. Rollback is automatic on uncaught exceptions. Success returns `jsonify(data)`; use marshmallow `schema.load()` for request parsing. The `type` token is the support-reportable code; raise value-add errors as `ApiError(code, description, type_, solution=...)` (renders itself); otherwise the token derives from the HTTP status phrase. Redirect-only OAuth routes handle redirects directly.
- MDRepo file uploads run as durable Kubernetes Jobs (`upload/submission.py`); credentials are passed to the worker via container environment variables in the Job manifest.

## Non-Obvious Gotchas

### Simulation Manifests (`.simulation.json`)
- **Single source of truth**: each manifest declares file roles (`run_input`, `reference_structure`, `trajectory` for GMX; `topology`, `coordinates`, `control`, `reference_structure`, `trajectory` for AMBER) and `extra_args`. Job models reference `simulation_path` — they no longer store file names.
- `list_simulation_files()` finds `*.simulation.json` anywhere under the experiment directory (not just `production/`).
- **Paths inside a manifest are relative to the manifest file's own directory** (notebooks write manifests next to their outputs); `_resolve_files()`/`resolve_role()` rebase them to experiment-relative paths, with an existence-checked experiment-relative fallback.
- `get_simulation()` validates against the JSON Schema referenced by `$schema` (which must be a mddash schema URL — see `manifest_schema.py`); invalid simulations are returned with errors and can't be used by downstream steps.
- A simulation is locked when its file is read-only or when a tuner/production job references its `simulation_path`. `mark_simulation_readonly()` chmods the file `0444`.
- Manifest `name` must be unique per experiment (wizard tab identity); `_new` is reserved (create-tab sentinel).
- **`step` IS the wizard phase index** (Setup 0, Tune 1, Run 2, Analyze 3) and `live` flags non-terminal tuner/production jobs (`JobStatus.is_live`); clients consume both directly — never decode ints or status strings client-side. A running job already advances to step 3 so partial trajectories can be analyzed mid-run. `Experiment._step_status` extends the same scale with publish = 4.

### Migrations
- `create_app()` runs `flask_migrate.upgrade()` on startup (skipped at head). Fresh databases are created by the same migrations — there is no `db.create_all()` fallback; a failed migration fails startup loudly. Add a migration file in `migrations/versions/` when adding columns. Do NOT manually run `flask db upgrade`.
- `db.Enum(PyEnum)` stores enum member NAMES in the DB (no `values_callable`, cf. 006), never `.value` strings — and SQLite emits no CHECK, so nothing rejects wrong values at write time. Migration DDL (`sa.Enum("PDB", ...)`) and any raw-SQL writes must use names; storing a value makes every ORM read of that row fail with LookupError.

### Authentication
- MDRepo OAuth tokens live in the Flask session, NOT the database. Use `MDRepoTokenManager(session).get_valid_token()`; refresh is automatic with exponential backoff (3 retries).

### Kubernetes
- **Lazy in-cluster config**: `config.load_incluster_config()` and client construction are deferred until first use — importing `clients.k8s` does NOT trigger K8s init. Tests must call `reset_k8s_clients_for_tests()` to clear cached clients between assertions.
- Jobs have `backoffLimit: 0` (no retries on failure).

### File Operations
- Git clones are shallow (`--depth 1`) with `.git` removed. Always validate paths with `check_path()`/`check_filename()` to prevent traversal. `is_excluded_path()` filters MDRepo uploads.
- Binder support: cloned repos may carry `environment.yml`/`requirements.txt`/`postBuild`; the notebook startup hook installs them at `/mddash/{experiment_id}/.binder-env`.

### Local Demo
- `make demo` runs the real API from `dashboard/api/_demo/` with mocked integrations and seeded data; all seeding, mock, and demo-state details live in `dashboard/api/_demo/AGENTS.md`.
