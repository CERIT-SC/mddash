# MDDash API

## Mission

Flask REST API that orchestrates molecular dynamics experiments across Kubernetes, manages MDRepo OAuth, and coordinates with external services (MDRun, Tuner). Runs as a sidecar in the user pod.

## Core Practices

- Business logic lives on SQLAlchemy models (e.g. `Experiment.from_pdb()`, `Experiment.publish()`).
- Routes raise `HTTPException` subclasses or marshmallow `ValidationError` — the global `@app.errorhandler` handlers (in `errors.py`, registered via `register_error_handlers(app)`) convert them to RFC 9457 problem-details responses: `{"type": "urn:mddash:<token>", "title": "<Problem>", "detail": "<Cause>"[, "solution"]}`. No `@handle_exceptions` decorator needed. Rollback is automatic on uncaught exceptions. Success returns `jsonify(data)`; use marshmallow `schema.load()` for request parsing. The `type` token is the support-reportable code; raise value-add errors as `ApiError(code, description, type_, solution=...)` (renders itself); otherwise the token derives from the HTTP status phrase. Redirect-only OAuth routes handle redirects directly.
- MDRepo file uploads run as durable Kubernetes Jobs (`upload/submission.py`); credentials are passed to the worker via container environment variables in the Job manifest.
- Experiment archive/restore/purge run as durable K8s Jobs mirroring the upload pattern (`archive/`, worker `dashboard/archive-worker`). Archives mirror the experiment at the bisync-excluded S3 prefix `_archives/<id>/` (server-side copy + filtered delta); `rclone check` gates local deletion. `archived_at` is set/cleared by reconciliation in the schema's `pre_dump`, which stashes the answer for `archive_state` to consume (one answer per payload); the durable markers are the DB columns, since the status doc dies with the dir and Jobs TTL-expire. Job liveness means "no terminal Complete/Failed condition" (Pending counts as live, or a slow start reads as failure); an in-flight doc with no live Job (`backoffLimit: 0`, unretried) reconciles to the direction's failed state, and failed submission removes only archive's own queued doc. Restore never gets an API-side doc (it would recreate the dir the worker copies into); a non-completed restore doc in a leftover dir is the retry sentinel: `restore()` and the worker continue it, a live Job outranks it, anything else in a present dir 409s/fails as clobber protection. Liveness lookups use `archive_status_cache` (1s TTL); submission writes the new Job through it for the 202's first poll.

## Non-Obvious Gotchas

### Simulation Manifests (`.simulation.json`)
- **Single source of truth**: each manifest declares file roles (`run_input`, `reference_structure`, `trajectory` for GMX; `topology`, `coordinates`, `control`, `reference_structure`, `trajectory` for AMBER) and `extra_args`. Job models reference `simulation_path` — they no longer store file names.
- `list_simulation_files()` finds `*.simulation.json` anywhere under the experiment directory (not just `production/`).
- **Paths inside a manifest are relative to the manifest file's own directory** (notebooks write manifests next to their outputs); `_resolve_files()`/`resolve_role()` rebase them to experiment-relative paths, with an existence-checked experiment-relative fallback. `write()`/`update()` strip the manifest-dir prefix from submitted values so stored manifests stay manifest-relative.
- `get_simulation()` validates against the JSON Schema referenced by `$schema` (which must be a mddash schema URL — see `manifest_schema.py`); invalid simulations are returned with errors and can't be used by downstream steps.
- A simulation is locked when its file is read-only or when a tuner/production job references its `simulation_path`. `mark_simulation_readonly()` chmods the file `0444`.
- Manifest `name` must be unique per experiment (wizard tab identity); `_new` is reserved (create-tab sentinel).
- **`step` IS the wizard phase index** (Setup 0, Tune 1, Run 2, Analyze 3) and `live` flags non-terminal tuner/production jobs (`JobStatus.is_live`); clients consume both directly — never decode ints or status strings client-side. A running job advances to step 3 once `nsteps_done` parses from the engine log (implies the run's files, trajectory included, exist), so partial trajectories can be analyzed mid-run; earlier finished/STOPPED segments also let a fresh segment start at step 3 (their data stays analyzable), and a STOPPED job with no live segment counts as step 3 "analyzing". `Experiment._step_status` extends the same scale with publish = 4.

### Run lifecycle (stop / extend / segments)
- **Segment history**: a simulation accumulates one `simulation_jobs` row per run/extension — every segment-scoped route (`GET`, `stop`, `extend`, `log`, `submit`) acts on the **latest row by `created_at`** (`SimulationJob.latest_for`; unknown verb suffixes are rejected by the `check_simulation_path` guard on the submit routes; AMBER has an explicit extend route that returns "GROMACS-only" 400); `DELETE` is the only operation that cascades, wiping all segments' MDRun jobs, rows, and result files (that is the destructive "Re-run" path). At most one live segment: rows are born PENDING and a partial unique index covers committed live statuses (`last_known_status IN ('PENDING','RUNNING','UNKNOWN')`) per `(experiment_id, simulation_path)` — live duplicates are impossible even under concurrent extends (the loser gets 400 and its orphaned MDRun job is torn down). NULL last_known_status is deliberately outside the index so legacy never-converged rows don't block the first extend or the migration.
- **Stop** (`POST .../gmx|amber/<path>/stop`) calls MDRun's stop endpoint and stores the status MDRun reports back (STOPPED, or FINISHED if the run beat the stop) — terminal via `JobStatus.is_terminal`, never file-cleaning, rows kept.
- **Extend** (`POST .../gmx/<path>/extend`, GMX only) submits a new segment with `-cpi <deffnm>.cpt -nsteps <delta>` on top of the manifest's extra_args (`utils.strip_run_control_args` strips `-nsteps`, rejects `-cpi` — the flow owns both flags). **Critical**: on a `-cpi` restart, mdrun's `-nsteps` counts *additional* steps from the checkpoint step — a cumulative value over-runs by all previous progress. The row instead persists the absolute target (`base + delta`) as `_nsteps`, **outranking** the manifest `-nsteps` override in the `nsteps` property (log step rows are absolute), and `base` as `_init_step` (appended logs never re-dump `init-step`, so the per-segment ETA needs the persisted resume point). The base is **actual progress** (the previous segment's `nsteps_done`, then frozen for display), falling back to the target — a stopped segment resumes from where it stood. It reuses the previous segment's hardware config, requires a real checkpoint on PVC, and never deletes files: `mdrun -cpi` appends, keeping one continuous trajectory per simulation.
- **Appended logs**: `mdrun -cpi` appends each segment's block to the same `.log` — full-file parsers take the **last** match, tail parsers use a **byte budget** (`utils.tail_bytes`) because engine trailers push markers past any line window. `performance` and the `nsteps_done` shortcut only trust a parse when `status == FINISHED` (a TERM-stopped run also prints a `Performance:` line). Extend freezes the outgoing segment's log-derived fields before submission so its history row keeps its own numbers.

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
