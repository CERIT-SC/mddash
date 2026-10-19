# MDDash API

## Mission

Fully async FastAPI service that orchestrates molecular dynamics experiments across Kubernetes, manages MDRepo OAuth, and coordinates with external services (MDRun, Tuner). Runs as a sidecar in the user pod.

## Layout

- `modules/<feature>/` packages own one feature each: `router.py` (FastAPI routes + OpenAPI metadata), `schemas.py` (request/response models), `service.py` (behavior), `models.py` (SQLAlchemy). Features: `system`, `experiments`, `publishing`, `archive`, `mdrepo`, `files`, `simulations`, `notebooks`, and `jobs/{gmx,amber,tuner,analysis}` (shared run base in `jobs/models.py`, `jobs/schemas.py`).
- `core/` holds what every feature shares: config, DB, errors, enums, caches, utils, validators, request dependencies, `problems()` response declarations, and base schemas. `clients/` holds the upstream clients (one class per upstream, bundled in `Clients`). `modules/models.py` imports every ORM model (registers all tables).
- `app.py` includes the module routers; their order is the path order of `openapi.yaml`.
- Data files stay at the API root: `notebook-modules.json` (read by migration 011) and `manifest_schemas/` (its GitHub URL is written into every manifest's `$schema`).

## Core practices

- **router → service → model.** Routers parse the request, call a service, and serialize. Services own behavior: upstream calls, orchestration, and queries on the request's `AsyncSession` (no repository layer). Models hold columns and derived properties that read only the row, its loaded jobs, and files. Services take `(session, clients)`, are injected with `Depends()` (`ExperimentServiceDep`, ...), and build the services they compose themselves.
- **Injected clients.** `create_app(clients=...)` takes the `Clients` bundle (production clients by default, sharing one `httpx.AsyncClient`); routes and services reach it through `ClientsDep`, never module globals. Tests pass clients over respx-mocked HTTP and AsyncMock Kubernetes APIs (`clients` fixture); patch a client method with `patch.object(clients.k8s, ...)` or on its class.
- Routes raise `core/errors.py` exceptions (`BadRequest`, `NotFound`, `Conflict`, ... or `ApiError(code, description, type_, solution=...)` for value-add tokens); handlers from `register_exception_handlers(app)` render RFC 9457 problem details `{"type": "urn:mddash:<token>", "title", "detail"[, "solution"]}`. Pydantic request validation renders as 400 `urn:mddash:validation-error`, never FastAPI's 422 shape. Uncommitted work rolls back when the request session closes.
- Request/response models live in each module's `schemas.py`; class names are the OpenAPI component names the UI client is generated from (renaming one renames a generated TS type). Inline enums use `enum_schema()` so generated clients keep field-derived names. `openapi.yaml` is generated (`make openapi`; `tests/contract` fails on drift), never hand-edited.
- **Request shape: refresh, serialize, commit.** Services fetch remote state (MDRun/tuner status, pods, archive Jobs, MDRepo) and record it on the model's transient attributes (`record_status()`, `record_pod()`, `record_archive_state()`); properties then only read rows, loaded jobs, and files, and fail loudly when read unrefreshed. Services gather refreshes concurrently (`ExperimentService.refresh()`, `JobsService.refresh()`), routers serialize via `core.dependencies.dump()`/`dump_many()` in a worker thread (properties parse logs/scan files), then commit values the properties cached on the rows. A property that raises during serialization is logged and its optional field falls back to its default (`core.schemas.OrmModel`).
- **Async ORM.** `expire_on_commit=False`; an experiment loads its notebook and jobs eagerly (`lazy="selectin"`, polymorphic selectin for GROMACS/AMBER columns). Child→experiment relationships are `raise_on_sql`: query jobs on their own through `Model.query()`, which loads the experiment. Set both `experiment_id` and `experiment` on new rows (file cleanup runs before the flush fills the FK).
- Blocking file/subprocess work runs in threads or `asyncio` subprocesses.
- MDRepo file uploads run as durable Kubernetes Jobs (`modules/publishing/submission.py`); credentials are passed to the worker via container environment variables in the Job manifest.
- Experiment archive/restore/purge run as durable K8s Jobs mirroring the upload pattern (`modules/archive/`, worker `dashboard/archive-worker`) at the bisync-excluded S3 prefix `_archives/<id>/`. Durable state is DB columns reconciled in `ArchiveService.refresh_state()` (the status doc dies with the dir, Jobs TTL-expire); restore retry keys off a non-completed status doc in the leftover dir. Worker/filter invariants (sync-vs-copy, sentinel no-write, doc exclusions) are test-pinned; design rationale lives in `docs/specs/2026-09-17-experiment-archivation-design.md`.

## Non-obvious gotchas

### Simulation manifests (`.simulation.json`)
- **Single source of truth.** Each manifest declares file roles (`run_input`, `reference_structure`, `trajectory` for GMX; `topology`, `coordinates`, `control`, `reference_structure`, `trajectory` for AMBER) and `extra_args`. Job models reference `simulation_path`. They no longer store file names.
- `list_simulation_files()` finds `*.simulation.json` anywhere under the experiment directory (not just `production/`).
- **Paths inside a manifest are relative to the manifest file's own directory** (notebooks write manifests next to their outputs); `_resolve_files()`/`resolve_role()` rebase them to experiment-relative paths, with an existence-checked experiment-relative fallback. `write()`/`update()` strip the manifest-dir prefix from submitted values so stored manifests stay manifest-relative.
- `get_simulation()` validates against the JSON Schema referenced by `$schema` (which must be a mddash schema URL, see `modules/simulations/manifest_schema.py`); invalid simulations are returned with errors and can't be used by downstream steps.
- A simulation is locked when its file is read-only or when a tuner/production job references its `simulation_path`. `mark_simulation_readonly()` chmods the file `0444`.
- Manifest `name` must be unique per experiment (wizard tab identity); `_new` is reserved (create-tab sentinel).
- **`step` is the wizard phase index** (Setup 0, Tune 1, Run 2, Analyze 3) and `live` flags non-terminal tuner/production jobs (`JobStatus.is_live`). Clients consume both directly. Never decode ints or status strings client-side. A running job advances to step 3 once `nsteps_done` parses from the engine log (the run's files, trajectory included, exist). Partial trajectories can be analyzed mid-run. A FINISHED or STOPPED job counts as step 3 "analyzing". `Experiment._step_status` extends the same scale with publish = 4.

### Run lifecycle (stop / extend)
- **One run per simulation.** `simulation_jobs` has at most one row per `(experiment_id, simulation_path)`, enforced by a DB unique constraint. The PK (`id`) is always the current MDRun job id. `submit` starts a run. A terminal run (finished/stopped/failed) is deleted and replaced (the destructive "Re-run" path, the UI confirms first). Only a live run 409s. `extend` continues a terminal run from its checkpoint by swapping the row in place (delete+insert carrying the cumulative `nsteps` and `init_step`). It keeps result files and the appended log. Concurrent inserts lose to the constraint. The loser rolls back, tears down its orphaned MDRun job, and gets 400 (extend) or 409 (submit). There is no run history. The engine log still appends across extensions, so full-file parsers take the last match (migration `014` collapsed legacy segment rows).
- **Stop** (`POST .../gmx|amber/<path>/stop`) calls MDRun's stop endpoint and stores the status MDRun reports back (STOPPED, or FINISHED if the run beat the stop). It is terminal via `JobStatus.is_terminal`, never file-cleaning, rows kept.
- **Extend** (`POST .../gmx/<path>/extend`, GMX only) starts a new MDRun job with `-cpi <deffnm>.cpt -nsteps <delta>` on top of the manifest's extra_args (`core.utils.strip_run_control_args` strips `-nsteps`, rejects `-cpi`, the flow owns both flags) and swaps the run row. On a `-cpi` restart, mdrun's `-nsteps` counts *additional* steps from the checkpoint step. A cumulative value over-runs by all previous progress. The row instead persists the absolute target (`base + delta`) as `_nsteps`, which outranks the manifest `-nsteps` override in the `nsteps` property (log step rows are absolute), and `base` as `_init_step` (appended logs never re-dump `init-step`, so the ETA needs the persisted resume point). The base is actual progress (the stopped run's `nsteps_done`), falling back to the target, so a stopped run resumes from where it stood. It reuses the run's hardware config, requires a real checkpoint on PVC, and never deletes files. `mdrun -cpi` appends, keeping one continuous trajectory per simulation.
- **Appended logs.** `mdrun -cpi` appends each extension's block to the same `.log`. Full-file parsers take the last match, tail parsers use a byte budget (`core.utils.tail_bytes`) because engine trailers push markers past any line window. `performance` and the `nsteps_done` shortcut only trust a parse when `status == FINISHED` (a TERM-stopped run also prints a `Performance:` line).

### Migrations
- The app lifespan runs `core.db.run_migrations()` before serving (skipped at head). Fresh databases are created by the same migrations. There is no `create_all()` fallback. A failed migration fails startup loudly. Add a migration file in `migrations/versions/` when adding columns. Do NOT run migrations manually.
- `db.Enum(PyEnum)` stores enum member NAMES in the DB (no `values_callable`, cf. 006), never `.value` strings. SQLite emits no CHECK, so nothing rejects wrong values at write time. Migration DDL (`sa.Enum("PDB", ...)`) and any raw-SQL writes must use names; storing a value makes every ORM read of that row fail with LookupError.

### Authentication
- MDRepo OAuth tokens live in the signed session cookie (Starlette `SessionMiddleware`, keyed by `MDREPO_CLIENT_SECRET`), NOT the database. Routes get the request's manager through `TokensDep` (`modules/mdrepo/dependencies.py`) and call `get_valid_token()` (or `get_credentials()` for the upload worker); refresh is automatic with exponential backoff (3 retries), serialized by an asyncio lock.

### Kubernetes
- **Lazy in-cluster config.** `K8sClient` defers the `kubernetes_asyncio` import, `load_incluster_config()`, and its `ApiClient` until the first API call and closes them on shutdown (`Clients.aclose()`); constructing it (every `create_app()`) touches no cluster config. Tests build it over AsyncMock Core/Batch APIs (`mock_k8s` fixture).
- Jobs have `backoffLimit: 0` (no retries on failure).

### File operations
- Git clones are shallow (`--depth 1`) with `.git` removed. Always validate paths with `check_path()`/`check_filename()` to prevent traversal. `is_excluded_path()` filters MDRepo uploads.
- Binder support: cloned repos may carry `environment.yml`/`requirements.txt`/`postBuild`; the notebook startup hook installs them at `/mddash/{experiment_id}/.binder-env`.

### Local demo
- `make demo` runs the real API from `dashboard/api/_demo/` with fake upstream clients and seeded data; all seeding, mock, and demo-state details live in `dashboard/api/_demo/AGENTS.md`.
