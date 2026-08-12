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
- `get_simulation()` validates against the JSON Schema referenced by `$schema` (which must be a mddash schema URL — see `manifest_schema.py`); invalid simulations are returned with errors and can't be used by downstream steps.
- A simulation is locked when its file is read-only or when a tuner/production job references its `simulation_path`. `mark_simulation_readonly()` chmods the file `0444`.
- Manifest `name` must be unique per experiment (wizard tab identity); `_new` is reserved (create-tab sentinel).

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
- Demo state persists at `MDDASH_DEMO_DATA_DIR` (default `/tmp/mddash`): on restart the seed path is skipped and `_rehydrate_runtime_state()` rebuilds in-memory job state from the SQLite DB. Rehydrated RUNNING jobs get a fresh `created_at` + 600s duration so they don't insta-finish, plus a fresh DB `start_timestamp` so `estimated_time` isn't inflated from the previous session.
- Running jobs show live progress: each mdrun status poll appends GMX log lines from `_demo/data/md.log` (deffnm = run_input minus `.tpr`, step table advances over the whole run, perf-summary/`Finished mdrun` tail appended only on completion; `Started/Finished mdrun` dates are stamped at write time) and rewrites the AMBER `.mdinfo` Nstep. Job logs are written lazily on first status poll because `Job.start()` cleans result files after submit.
- The seeded running tuner rolls forever: the mock keeps a rolling window of `max_trials` trials (dropping the oldest) instead of reaching FINISHED, so sustained polling never burns it out; FINISH/ERROR alternates by each trial's creation `seq`, not its list index (the window would otherwise pin every new trial to the same odd index). The seeded stopped NPT tuner covers the finished-state UI. MDRepo publish is fully simulated: `/mdrepo/auth` bypasses OAuth with a demo session token; the upload "Job" is a background thread that writes a `completed` upload-status file after ~4s.
- K8s is mocked by mutating `clients.k8s` functions (not by patching the `kubernetes` lib — `load_incluster_config` is lazy, so patching the library class before import does nothing). `check_quota_headroom`, `count_notebook_pods`, `read_job`, `wait_for_pod_admission` etc. are all neutralized in `_demo/mocks/k8s.py`.
- Restart-safe against an existing `MDDASH_DEMO_DATA_DIR` (default `/tmp/mddash`): rehydration overwrites read-only-locked manifests and keeps running jobs running. Wipe the dir for a pristine seed.
- Running jobs show live progress: each status poll advances the gmx `.log` (template in `_demo/data/md.log`) or the AMBER `.mdinfo`. Job logs/stdio are written lazily on first poll because `Job.start()` result-file cleanup would delete anything written at submit time.
- MDRepo publish is fully simulated: `/mdrepo/auth` bypass sets a demo session token; the upload "Job" completes in ~4s via a mock K8s worker thread.
