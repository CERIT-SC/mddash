# AMBER Engine Support Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add AMBER MD engine support alongside GROMACS across the full wizard workflow, with engine selected at experiment creation and immutable thereafter.

**Architecture:** Engine-dispatcher pattern — each wizard step resolves a per-engine panel component; backend uses Joined Table Inheritance for simulation jobs (`simulation_jobs` base + `gromacs_jobs` + `amber_jobs`); MDRun API gets symmetric per-engine routes mirroring the tuner pattern.

**Tech Stack:** Flask/SQLAlchemy (JTI, Alembic migration), Marshmallow (polymorphic schemas), React/TypeScript (discriminated union types, dispatcher components), TanStack Query (new `use-amber.ts` hook file).

**Design spec:** `docs/specs/2026-04-15-amber-engine-support-design.md`

---

## File Map

### New files
| File | Purpose |
|------|---------|
| `dashboard/api/enums/engine.py` | `Engine`, `AmberBinary`, `EwaldPreset` enums |
| `dashboard/api/models/simulation_job.py` | `SimulationJob` JTI base model |
| `dashboard/api/models/amber_job.py` | `AmberJob` JTI subclass |
| `dashboard/api/schemas/simulation_job.py` | Polymorphic `SimulationJobSchema` |
| `dashboard/api/schemas/amber_job.py` | `AmberJobSchema` |
| `dashboard/api/routes/amber.py` | `amber_bp` blueprint |
| `dashboard/api/migrations/versions/003_amber_engine.py` | Data migration |
| `dashboard/ui/src/hooks/use-amber.ts` | AMBER job hooks |
| `dashboard/ui/src/components/Wizard/RunStep/GmxRunPanel.tsx` | Extracted GMX run panel |
| `dashboard/ui/src/components/Wizard/RunStep/AmberRunPanel.tsx` | AMBER run panel |
| `dashboard/ui/src/components/Wizard/RunStep/AmberRunView.tsx` | AMBER run view |
| `dashboard/ui/src/components/Wizard/RunStep/AmberStartForm.tsx` | AMBER start form |
| `dashboard/ui/src/components/Wizard/TuneStep/GmxTunePanel.tsx` | Extracted GMX tune panel |
| `dashboard/ui/src/components/Wizard/TuneStep/AmberTunePanel.tsx` | AMBER tune panel |
| `dashboard/ui/src/components/Wizard/TuneStep/AmberTunerView.tsx` | AMBER tuner view |
| `dashboard/ui/src/components/Wizard/TuneStep/AmberTunerTable.tsx` | AMBER trial table |
| `dashboard/ui/src/components/Wizard/AmberInputSelector.tsx` | 3-file input selector |
| `dashboard/ui/src/components/Wizard/AnalyzeStep/engine-analyze-config.ts` | Per-engine file extension config |

### Modified files
| File | Change summary |
|------|---------------|
| `dashboard/api/enums/__init__.py` | Export `Engine`, `AmberBinary`, `EwaldPreset` |
| `dashboard/api/models/__init__.py` | Export `SimulationJob`, `AmberJob` |
| `dashboard/api/models/experiment.py` | Add `engine` column; `simulation_jobs` relationship; update `_step_status` and `delete` |
| `dashboard/api/models/gromacs_job.py` | Refactor as `GromacsJob(SimulationJob)` JTI subclass; move shared columns to base |
| `dashboard/api/models/tuner_job.py` | Add `engine`, `inpcrd_name`, `mdin_name`; dispatch in `start`/`_status`/`stop`/`delete` |
| `dashboard/api/schemas/__init__.py` | Export new schemas |
| `dashboard/api/schemas/experiment.py` | Replace `gromacs_jobs` field with `simulation_jobs` |
| `dashboard/api/routes/__init__.py` | Register `amber_bp` |
| `dashboard/api/routes/experiments.py` | Accept `engine` field on `create_experiment` |
| `dashboard/api/routes/tuner.py` | Accept `inpcrd_name`/`mdin_name` params; dispatch trial log routes by engine |
| `dashboard/api/clients/mdrun.py` | Add `create_amber_job`, `get_gmx_job`, `get_amber_job`, `delete_gmx_job`, `delete_amber_job`; update URLs |
| `dashboard/api/cache.py` | Add `simulation_status_cache` (replaces `gromacs_status_cache` for base) |
| `dashboard/api/tests/conftest.py` | Import and register `amber_bp` |
| `mdrun-api/config.py` | Add `AMBER_IMAGE` env var |
| `mdrun-api/k8s_client.py` | Add `create_amber_job()` |
| `mdrun-api/schemas.py` | Rename to `GmxJobCreateRequestSchema`; add `AmberJobCreateRequestSchema` |
| `mdrun-api/routes.py` | Split into `gmx_bp` + `amber_bp`; shared `_get_job`/`_delete_job` handlers |
| `mdrun-api/tests/conftest.py` | Update imports for renamed blueprints |
| `dashboard/ui/src/util/types.ts` | Add `Engine`, `AmberJob`, `AmberTunerTrial`; update `Experiment`, `TunerJob` |
| `dashboard/ui/src/util/const.ts` | Add `Engine` constant object |
| `dashboard/ui/src/hooks/use-gromacs.ts` | No logic changes; consumed by `GmxRunPanel` |
| `dashboard/ui/src/hooks/use-tuner.ts` | Add `useRunAmberTuner` mutation |
| `dashboard/ui/src/hooks/use-experiments.ts` | Pass `engine` field in `createExperiment` FormData |
| `dashboard/ui/src/components/Wizard/RunStep/RunStep.tsx` | Replace body with engine dispatcher |
| `dashboard/ui/src/components/Wizard/RunStep/RunView.tsx` | Rename import `StartForm` → `GmxStartForm` |
| `dashboard/ui/src/components/Wizard/RunStep/StartForm.tsx` | Rename file to `GmxStartForm.tsx` |
| `dashboard/ui/src/components/Wizard/TuneStep/TuneStep.tsx` | Replace body with engine dispatcher |
| `dashboard/ui/src/components/Wizard/AnalyzeStep/AnalyzeStep.tsx` | Read per-engine config for file filters |
| `dashboard/ui/src/components/Wizard/AnalyzeStep/AnalyzeSidebar.tsx` | Accept `structureExts`/`trajectoryExts` as props |
| `dashboard/ui/src/pages/New.tsx` | Add engine selector above Initial Data |

---

## Phase 1 — Backend Foundation

### Task 1: Engine enums

**Files:**
- Create: `dashboard/api/enums/engine.py`
- Modify: `dashboard/api/enums/__init__.py`

- [ ] Create `engine.py` with three `str, Enum` classes:
  - `Engine` — values `"gmx"` and `"amber"`
  - `AmberBinary` — values `"pmemd.cuda"` and `"pmemd.MPI"`
  - `EwaldPreset` — values `"default"` and `"optimized"`
- [ ] Export all three from `enums/__init__.py` alongside existing enums
- [ ] Verify import works: `cd dashboard/api && python -c "from enums import Engine, AmberBinary, EwaldPreset; print('ok')"`
  Expected: `ok`
- [ ] Commit: `git commit -m "feat(api): add Engine, AmberBinary, EwaldPreset enums"`

---

### Task 2: SimulationJob JTI base model

**Files:**
- Create: `dashboard/api/models/simulation_job.py`

The `SimulationJob` table (`simulation_jobs`) holds all columns shared between engines:
- `id` (String 36, PK), `experiment_id` (FK), `created_at`, `engine` (JTI discriminator)
- `np`, `ntomp`, `extra_args`
- `_start_timestamp`, `_finish_timestamp`, `_nsteps`, `_performance`, `_last_known_status`

Key methods on the base class:
- `status` property — dispatches `mdrun.get_gmx_job` or `mdrun.get_amber_job` based on `self.engine`; uses `simulation_status_cache` from `cache.py`
- `delete()` — dispatches `mdrun.delete_gmx_job` or `mdrun.delete_amber_job`, then calls `self._cleanup_files()` (no-op in base)
- `_cleanup_files()` — virtual, empty in base, overridden in subclasses
- `experiment` relationship back-ref (to be wired once `Experiment` is updated)

Add `simulation_status_cache: TTLCache = TTLCache(maxsize=100, ttl=1)` to `dashboard/api/cache.py`.

- [ ] Add `simulation_status_cache` to `cache.py`
- [ ] Create `simulation_job.py` with `SimulationJob(db.Model)` using `__mapper_args__ = {"polymorphic_on": "engine"}`
- [ ] Add to `models/__init__.py` exports
- [ ] Verify: `python -c "from models import SimulationJob; print('ok')"`
  Expected: `ok`
- [ ] Commit: `git commit -m "feat(api): add SimulationJob JTI base model"`

---

### Task 3: Refactor GromacsJob as JTI subclass

**Files:**
- Modify: `dashboard/api/models/gromacs_job.py`

`GromacsJob` becomes `GromacsJob(SimulationJob)` with:
- `__tablename__ = "gromacs_jobs"`
- `__mapper_args__ = {"polymorphic_identity": Engine.GMX}`
- `id: Mapped[str] = mapped_column(ForeignKey("simulation_jobs.id"), primary_key=True)`
- Engine-specific columns only: `tpr_name`, `pme`, `nb`
- Remove columns now on base: `experiment_id`, `created_at`, `np`, `ntomp`, `extra_args`, all `_*` status/perf columns
- Remove `status` property and `delete()` method (moved to base)
- Keep: `start()`, `get_log()`, all `_parse_*` methods, `_cleanup_previous_results()`, `_cleanup_files()` override
- The `experiment` relationship is now on the base; remove it from `GromacsJob`

- [ ] Rewrite `gromacs_job.py` as JTI subclass per above
- [ ] Run existing tests: `cd dashboard/api && python -m pytest tests/ -x -q`
  Expected: all tests pass (or skip any that need amber_bp — wire that in Task 10)
- [ ] Commit: `git commit -m "refactor(api): convert GromacsJob to JTI subclass of SimulationJob"`

---

### Task 4: AmberJob JTI subclass

**Files:**
- Create: `dashboard/api/models/amber_job.py`
- Modify: `dashboard/api/models/__init__.py`

`AmberJob(SimulationJob)` with:
- `__tablename__ = "amber_jobs"`, `polymorphic_identity = Engine.AMBER`
- `id` FK to `simulation_jobs.id`
- Engine-specific columns: `prmtop_name`, `inpcrd_name`, `mdin_name`, `binary (Enum AmberBinary)`, `ewald (Enum EwaldPreset)`
- `RESULT_EXTENSIONS = ["nc", "rst7", "mdinfo", "out"]`
- `start()` classmethod — calls `mdrun.create_amber_job(...)`, creates `AmberJob` DB record
- `get_log(type)` — supports `"stdout"` and `"stderr"` only (no GMX log)
- `_parse_performance()` — reads `_stdout_log`, finds line matching `ns/day =\s+([\d.]+)`
- `_parse_nsteps_done()` — reads last `NSTEP =\s+(\d+)` from `_stdout_log`
- `_cleanup_files()` — deletes AMBER result files by `RESULT_EXTENSIONS`
- Log file paths follow same `mdrun-{id}.out` / `mdrun-{id}.err` convention

- [ ] Create `amber_job.py`
- [ ] Export `AmberJob` from `models/__init__.py`
- [ ] Verify: `python -c "from models import AmberJob; print('ok')"`
  Expected: `ok`
- [ ] Commit: `git commit -m "feat(api): add AmberJob JTI subclass"`

---

### Task 5: Experiment model — engine column + simulation_jobs relationship

**Files:**
- Modify: `dashboard/api/models/experiment.py`

Changes:
- Add `engine: Mapped[Engine] = mapped_column(db.Enum(Engine), nullable=False, default=Engine.GMX)`
- Replace `gromacs_jobs` relationship with `simulation_jobs` pointing at `SimulationJob`; keep `cascade="all, delete-orphan"`
- Update `_step_status()`: replace all `self.gromacs_jobs` references with `self.simulation_jobs`; add engine-agnostic step detection (check `SimulationJob.query.filter_by(experiment_id=self.id)` or use `self.simulation_jobs`)
- Update `delete()`: iterate `self.simulation_jobs` instead of `self.gromacs_jobs`
- Update docstring to remove `gromacs_jobs` attribute, add `simulation_jobs` and `engine`

Note: Keep the `TYPE_CHECKING` import of `GromacsJob` → replace with `SimulationJob`.

- [ ] Edit `experiment.py` as described
- [ ] Run tests: `cd dashboard/api && python -m pytest tests/ -x -q`
  Expected: pass
- [ ] Commit: `git commit -m "feat(api): add engine column and simulation_jobs relationship to Experiment"`

---

### Task 6: TunerJob engine dispatch

**Files:**
- Modify: `dashboard/api/models/tuner_job.py`

New columns (will be applied by migration in Task 7):
- `engine: Mapped[Engine]` — `nullable=False, default=Engine.GMX`
- `inpcrd_name: Mapped[str | None]` — nullable, AMBER only
- `mdin_name: Mapped[str | None]` — nullable, AMBER only

`tpr_name` stays as-is; for AMBER jobs it stores the `.prmtop` path (internal only).

Dispatch in each method via `match self.engine: case Engine.GMX: ... case Engine.AMBER: ...`:
- `start()` — GMX calls `tuner.gmx_submit(tpr_path, ...)`, AMBER calls `tuner.amber_submit(tpr_path, inpcrd_path, mdin_path, ...)`
- `_status()` — GMX calls `tuner.gmx_poll_status`, AMBER calls `tuner.amber_poll_status`
- `stop()` / `delete()` — both engines use same tuner delete call (tuner API is symmetric)

Update `TunerJob.start()` classmethod signature to accept `engine`, `inpcrd_path`, `mdin_path` (optional, default `None`).

- [ ] Add columns and dispatch logic to `tuner_job.py`
- [ ] Run tests: `cd dashboard/api && python -m pytest tests/ -x -q`
  Expected: pass
- [ ] Commit: `git commit -m "feat(api): add engine dispatch to TunerJob"`

---

### Task 7: Database migration 003

**Files:**
- Create: `dashboard/api/migrations/versions/003_amber_engine.py`

Migration steps (all use `op.batch_alter_table` for SQLite compatibility):

1. **Create `simulation_jobs` table** — all shared columns with `engine` defaulting to `'gmx'`
2. **Populate `simulation_jobs`** from existing `gromacs_jobs` rows using `op.execute(...)`:
   ```sql
   INSERT INTO simulation_jobs (id, experiment_id, created_at, engine, np, ntomp, extra_args,
       start_timestamp, finish_timestamp, nsteps, performance, last_known_status)
   SELECT id, experiment_id, created_at, 'gmx', np, ntomp, extra_args,
       start_timestamp, finish_timestamp, nsteps, performance, last_known_status
   FROM gromacs_jobs
   ```
3. **Rebuild `gromacs_jobs`** via `batch_alter_table`: drop migrated columns; add FK `id → simulation_jobs.id`
4. **Create `amber_jobs` table** — `id` FK to `simulation_jobs`, plus AMBER-specific columns
5. **Add `engine` column to `experiments`** — `NOT NULL`, server default `'gmx'`
6. **Add AMBER columns to `tuner_jobs`** — `engine` (default `'gmx'`), `inpcrd_name` (nullable), `mdin_name` (nullable)

`downgrade()` reverses each step in reverse order. Revision chain: `down_revision = "002"`.

- [ ] Write migration `003_amber_engine.py` following the pattern from `002_notebook_tiers.py`
- [ ] Verify migration runs: `cd dashboard/api && python -c "from app import create_app; app = create_app(); print('migration ok')"`
  Expected: `migration ok` (no errors in output)
- [ ] Commit: `git commit -m "feat(api): migration 003 — simulation_jobs JTI + amber columns"`

---

### Task 8: Schemas

**Files:**
- Create: `dashboard/api/schemas/simulation_job.py`
- Create: `dashboard/api/schemas/amber_job.py`
- Modify: `dashboard/api/schemas/experiment.py`
- Modify: `dashboard/api/schemas/__init__.py`

`SimulationJobSchema` — polymorphic auto-schema for `SimulationJob`; marshmallow-sqlalchemy resolves to the correct subclass automatically via JTI.

`AmberJobSchema` — same pattern as `GromacsJobSchema`:
```python
class AmberJobSchema(BaseAutoSchema):
    class Meta:
        model = AmberJob
        load_instance = True
        include_fk = True
```

`ExperimentSchema` — replace `gromacs_jobs = fields.Nested("GromacsJobSchema", many=True)` with `simulation_jobs = fields.Nested("SimulationJobSchema", many=True)`.

Export both new schemas from `schemas/__init__.py`.

- [ ] Create both schema files and update `experiment.py` + `__init__.py`
- [ ] Verify: `python -c "from schemas import SimulationJobSchema, AmberJobSchema; print('ok')"`
  Expected: `ok`
- [ ] Commit: `git commit -m "feat(api): add SimulationJobSchema, AmberJobSchema; update ExperimentSchema"`

---

### Task 9: amber_bp routes

**Files:**
- Create: `dashboard/api/routes/amber.py`

Mirror `routes/gmx.py` exactly in structure. Five routes under `url_prefix = f"{API_PREFIX}/experiments/<experiment_id>/amber"`:

| Method | Path | Handler |
|--------|------|---------|
| GET | `` | `list_amber_jobs` — query `AmberJob.filter_by(experiment_id=...)` |
| GET | `/<path:prmtop_name>` | `get_amber_job` — lookup by `experiment_id + prmtop_name` |
| POST | `/<path:prmtop_name>` | `submit_amber_job` — form fields: `inpcrd_name`, `mdin_name`, `binary`, `np`, `ntomp`, `ewald`, `extra_args`; calls `AmberJob.start(...)` |
| DELETE | `/<path:prmtop_name>` | `delete_amber_job` |
| GET | `/<path:prmtop_name>/log` | `get_amber_log` — `type` query param: `stdout` or `stderr` |

All handlers use `@handle_exceptions()` (with `rollback=True` for POST/DELETE).

- [ ] Write `amber.py`
- [ ] Commit (routes wired in next task): `git commit -m "feat(api): add amber_bp routes"`

---

### Task 10: Wire remaining route + test changes

**Files:**
- Modify: `dashboard/api/routes/__init__.py`
- Modify: `dashboard/api/routes/experiments.py`
- Modify: `dashboard/api/routes/tuner.py`
- Modify: `dashboard/api/tests/conftest.py`

**`routes/__init__.py`:** Import and export `amber_bp`.

**`routes/experiments.py` — `create_experiment`:** Read `engine = form.get("engine", "gmx")`; validate it's a valid `Engine` value; pass `engine=Engine(engine)` to all three factory methods (`from_pdb`, `from_repo`, `from_files`). Update each factory classmethod on `Experiment` to accept and persist `engine`.

**`routes/tuner.py` — `start_tuner_job`:** Read `inpcrd_name = request.args.get("inpcrd_name")` and `mdin_name = request.args.get("mdin_name")`; pass to `TunerJob.start(experiment, tpr_path, ..., engine=experiment.engine, inpcrd_path=..., mdin_path=...)`.

**`routes/tuner.py` — `get_trial_stdout/stderr`:** Dispatch based on `tuner_job.engine`:
```python
match tuner_job.engine:
    case Engine.GMX:  stdout = tuner.gmx_get_trial_stdout(...)
    case Engine.AMBER: stdout = tuner.amber_get_trial_stdout(...)
```

**`tests/conftest.py`:** Add `amber_bp` to the imports block and register it in the `app` fixture.

- [ ] Apply all four file changes
- [ ] Run full test suite: `cd dashboard/api && python -m pytest tests/ -v`
  Expected: all existing tests pass
- [ ] Commit: `git commit -m "feat(api): wire amber_bp; accept engine on creation; dispatch tuner trial logs"`

---

## Phase 2 — MDRun API

### Task 11: MDRun API — amber K8s job + config

**Files:**
- Modify: `mdrun-api/config.py`
- Modify: `mdrun-api/k8s_client.py`

**`config.py`:** Add `AMBER_IMAGE = os.environ.get("AMBER_IMAGE", "cerit.io/xkrasa/amber:24")`. Add warning log if unset.

**`k8s_client.py` — `create_amber_job()`:** Follows the same structure as `create_gromacs_job()`:
- S3 init container downloads `prmtop`, `inpcrd`, `mdin` files from S3
- Main container uses `AMBER_IMAGE`; command dispatches on `binary`:
  - `pmemd.cuda`: `pmemd.cuda -O -i {mdin} -o {name}.out -p {prmtop} -c {inpcrd} -r {name}.rst7 -x {name}.nc`
  - `pmemd.MPI`: `mpirun -np {np} pmemd.MPI -O ...` same flags
- Stdout/stderr redirected to `{name}.out` and `{name}.err` (same naming as GMX)
- S3 sync sidecar uploads result extensions: `nc`, `rst7`, `mdinfo`, `out`
- Same security context (UID 1000, non-root), same `backoffLimit: 0`
- GPU resource requested only for `pmemd.cuda` binary

- [ ] Add `AMBER_IMAGE` to `config.py`
- [ ] Add `create_amber_job(ns, bucket_name, name, experiment_id, prmtop_name, inpcrd_name, mdin_name, binary, np, ntomp, extra_args)` to `k8s_client.py`
- [ ] Commit: `git commit -m "feat(mdrun): add create_amber_job k8s manifest"`

---

### Task 12: MDRun API — schema + route restructure

**Files:**
- Modify: `mdrun-api/schemas.py`
- Modify: `mdrun-api/routes.py`
- Modify: `mdrun-api/tests/conftest.py`

**`schemas.py`:** Rename `JobCreateRequestSchema` → `GmxJobCreateRequestSchema`. Add `AmberJobCreateRequestSchema` with fields: `experiment_id`, `prmtop_name`, `inpcrd_name`, `mdin_name`, `bucket_name`, `binary`, `np`, `ntomp`, `ewald`, `extra_args`.

**`routes.py`:** Split `mdrun_bp` into two blueprints:
```python
gmx_bp   = Blueprint("gmx",   __name__, url_prefix=f"{API_PREFIX}/jobs/gmx")
amber_bp = Blueprint("amber", __name__, url_prefix=f"{API_PREFIX}/jobs/amber")
```

Shared internal functions (not routes):
```python
def _get_job(job_id: str) -> Response: ...
def _delete_job(job_id: str) -> Response: ...
```

Each blueprint registers GET `/<job_id>` and DELETE `/<job_id>` pointing to the shared handlers. Each blueprint also gets its own POST `/` route with the appropriate schema and `create_and_start` call.

Register both in `app.py` (replace the single `mdrun_bp` registration).

**`tests/conftest.py`:** Update the module-level import to use `gmx_bp, amber_bp` (instead of `mdrun_bp`). Register both in the `app` fixture. Update `mock_k8s_client` to also mock `create_amber_job`.

- [ ] Apply all changes
- [ ] Run MDRun tests: `cd mdrun-api && python -m pytest tests/ -v`
  Expected: all existing tests pass with updated route paths (`/api/jobs/gmx/...`)
- [ ] Commit: `git commit -m "feat(mdrun): symmetric per-engine routes gmx_bp + amber_bp"`

---

## Phase 3 — Dashboard API mdrun client

### Task 13: Update mdrun client

**Files:**
- Modify: `dashboard/api/clients/mdrun.py`

Changes:
- Update `create_job()` URL: `/jobs` → `/jobs/gmx`; rename to `create_gmx_job()` (keep old name as alias or update all callers in `GromacsJob.start()`)
- Add `create_amber_job(experiment_id, prmtop_name, inpcrd_name, mdin_name, bucket_name, binary, np, ntomp, ewald, extra_args)` → `POST {MDRUN_API_URL}/jobs/amber`
- Add `get_gmx_job(job_id)` → `GET /jobs/gmx/{id}`
- Add `get_amber_job(job_id)` → `GET /jobs/amber/{id}`
- Add `delete_gmx_job(job_id)` → `DELETE /jobs/gmx/{id}`
- Add `delete_amber_job(job_id)` → `DELETE /jobs/amber/{id}`
- Keep old `get_job` / `delete_job` as internal aliases or remove (update `SimulationJob.status` and `SimulationJob.delete()` to call the typed variants)

- [ ] Update `clients/mdrun.py`
- [ ] Update `SimulationJob.status` and `SimulationJob.delete()` to call `get_gmx_job`/`get_amber_job` and `delete_gmx_job`/`delete_amber_job`
- [ ] Run tests: `cd dashboard/api && python -m pytest tests/ -v`
  Expected: pass
- [ ] Commit: `git commit -m "feat(api): update mdrun client for per-engine URLs"`

---

## Phase 4 — UI Types & New Experiment Form

### Task 14: TypeScript types and Engine constant

**Files:**
- Modify: `dashboard/ui/src/util/types.ts`
- Modify: `dashboard/ui/src/util/const.ts`

**`const.ts`:** Add at the top (before `DEBUG`):
```typescript
export const Engine = { GMX: "gmx", AMBER: "amber" } as const
export type Engine = typeof Engine[keyof typeof Engine]
```

**`types.ts`:**
- Add `engine: Engine` to `Experiment`
- Replace `gromacs_jobs: GromacsJob[]` with `simulation_jobs: SimulationJob[]`
- Add `AmberBinary = "pmemd.cuda" | "pmemd.MPI"` type alias
- Add `EwaldPreset = "default" | "optimized"` type alias
- Add `AmberJob` interface with fields from spec
- Add `GmxTunerTrial` (rename existing `TunerTrial`) and `AmberTunerTrial` interfaces
- Add `SimulationJob = GromacsJob | AmberJob` discriminated union (discriminant: `engine`)
- Update `TunerJob`: add `engine: Engine`; change `trials: GmxTunerTrial[] | AmberTunerTrial[]`

- [ ] Update both files
- [ ] Type-check: `cd dashboard/ui && npx tsc --noEmit 2>&1 | head -40`
  Expected: errors only in files that reference removed `gromacs_jobs` (fix those in later tasks)
- [ ] Commit: `git commit -m "feat(ui): add Engine type, AmberJob, updated Experiment types"`

---

### Task 15: Engine selector on New experiment page

**Files:**
- Modify: `dashboard/ui/src/pages/New.tsx`

Add `engine` state (default `"gmx"`). Insert a `ToggleGroup` or segmented `Tabs` control above the "Initial Data" section:

```tsx
<div className="flex flex-col gap-1">
  <Label>MD Engine</Label>
  <Tabs value={engine} onValueChange={(v) => setEngine(v as Engine)}>
    <TabsList className="w-full">
      <TabsTrigger value="gmx" className="flex-1">GROMACS</TabsTrigger>
      <TabsTrigger value="amber" className="flex-1">AMBER</TabsTrigger>
    </TabsList>
  </Tabs>
</div>
```

In `handleSubmit`, append `formData.append("engine", engine)` before calling `createExperiment.mutate`.

- [ ] Add `engine` state and selector to `New.tsx`
- [ ] Type-check: `npx tsc --noEmit`
- [ ] Commit: `git commit -m "feat(ui): add engine selector to New experiment form"`

---

### Task 16: AMBER hooks + useRunAmberTuner

**Files:**
- Create: `dashboard/ui/src/hooks/use-amber.ts`
- Modify: `dashboard/ui/src/hooks/use-tuner.ts`

**`use-amber.ts`:** Mirror the shape of `use-gromacs.ts` exactly, substituting `amber` endpoints and `AmberJob` types:
- `useAmberStatuses(experimentId)` — `GET /experiments/{id}/amber`
- `useAmberStatus(experimentId, prmtopName)` — with 5 s polling (stop on TERMINATED/ERROR)
- `useSubmitAmber(experimentId)` — `POST /experiments/{id}/amber/{name}`
- `useDeleteAmber(experimentId)` — `DELETE /experiments/{id}/amber/{name}`
- `useAmberLogs(experimentId, prmtopName, logType, shouldPoll)` — `logType: "stdout" | "stderr"`

**`use-tuner.ts`:** Add `useRunAmberTuner(experimentId)` mutation:
```typescript
interface RunAmberTunerVariables {
  prmtopName: string
  inpcrdName: string
  mdinName: string
  nsteps?: number
}
```
Posts to `/experiments/{id}/tuner/{prmtopName}` with `inpcrd_name`, `mdin_name`, `nsteps` as query params; invalidates tuner query cache on success.

- [ ] Create `use-amber.ts`
- [ ] Add `useRunAmberTuner` to `use-tuner.ts`
- [ ] Type-check: `npx tsc --noEmit`
- [ ] Commit: `git commit -m "feat(ui): add use-amber hooks and useRunAmberTuner"`

---

## Phase 5 — Extract GMX Components + Dispatchers

### Task 17: Extract GmxRunPanel + make RunStep a dispatcher

**Files:**
- Rename: `StartForm.tsx` → `GmxStartForm.tsx` (update import in `RunView.tsx`)
- Create: `dashboard/ui/src/components/Wizard/RunStep/GmxRunPanel.tsx`
- Modify: `dashboard/ui/src/components/Wizard/RunStep/RunStep.tsx`
- Modify: `dashboard/ui/src/components/Wizard/RunStep/RunView.tsx`

**`GmxRunPanel.tsx`:** Move the entire current body of `RunStep.tsx` into this file verbatim. It receives `WizardStepProps` and renders the TPR selector + `RunView`.

**`RunStep.tsx`:** Replace body with engine dispatcher:
```tsx
import type { ComponentType } from "react"
import { Engine } from "@/util/const"
import type { WizardStepProps } from "@/components/Wizard/Stepper"
import GmxRunPanel from "./GmxRunPanel"
import AmberRunPanel from "./AmberRunPanel"

const ENGINE_PANELS: Record<Engine, ComponentType<WizardStepProps>> = {
  [Engine.GMX]: GmxRunPanel,
  [Engine.AMBER]: AmberRunPanel,
}

const RunStep = (props: WizardStepProps) => {
  const Panel = ENGINE_PANELS[props.experiment.engine]
  return <Panel {...props} />
}
export default RunStep
```

Note: `AmberRunPanel` is created in Task 19; TypeScript will error until then — that's OK, will fix when AmberRunPanel exists.

**`RunView.tsx`:** Update import `StartForm` → `GmxStartForm`.

- [ ] Rename `StartForm.tsx` to `GmxStartForm.tsx`; update the import in `RunView.tsx`
- [ ] Create `GmxRunPanel.tsx` with moved content
- [ ] Replace `RunStep.tsx` with dispatcher (tolerate the `AmberRunPanel` missing-import error for now)
- [ ] Type-check: `npx tsc --noEmit` — expect only the `AmberRunPanel` missing-module error
- [ ] Commit: `git commit -m "refactor(ui): extract GmxRunPanel; make RunStep an engine dispatcher"`

---

### Task 18: Extract GmxTunePanel + make TuneStep a dispatcher

**Files:**
- Create: `dashboard/ui/src/components/Wizard/TuneStep/GmxTunePanel.tsx`
- Modify: `dashboard/ui/src/components/Wizard/TuneStep/TuneStep.tsx`

Same extraction pattern as Task 17:
- Move full `TuneStep.tsx` body to `GmxTunePanel.tsx` (receives `WizardStepProps`, renders TPR selector + `TunerView` + Skip button + confirm dialogs)
- Replace `TuneStep.tsx` body with dispatcher over `ENGINE_PANELS = { gmx: GmxTunePanel, amber: AmberTunePanel }`

- [ ] Create `GmxTunePanel.tsx` with moved content
- [ ] Replace `TuneStep.tsx` with dispatcher
- [ ] Type-check: expect only `AmberTunePanel` missing-module error
- [ ] Commit: `git commit -m "refactor(ui): extract GmxTunePanel; make TuneStep an engine dispatcher"`

---

## Phase 6 — AMBER UI Components

### Task 19: AmberInputSelector (shared 3-file selector)

**Files:**
- Create: `dashboard/ui/src/components/Wizard/AmberInputSelector.tsx`

Props:
```typescript
interface AmberInputSelectorProps {
  experimentId: string
  selectedPrmtop: string | null
  selectedInpcrd: string | null
  selectedMdin: string | null
  onPrmtopSelected: (name: string) => void
  onInpcrdSelected: (name: string) => void
  onMdinSelected: (name: string) => void
}
```

Renders three stacked `FileSelector` components:
1. `ext={["prmtop", "parm7"]}` → topology
2. `ext={["inpcrd", "rst7", "nc"]}` → coordinates
3. `ext={["mdin"]}` → run control

Wrapped in a `Card` with title "AMBER Inputs". Display the selected file names below each selector.

- [ ] Create `AmberInputSelector.tsx`
- [ ] Type-check: `npx tsc --noEmit`
- [ ] Commit: `git commit -m "feat(ui): add AmberInputSelector component"`

---

### Task 20: AmberRunPanel + AmberStartForm + AmberRunView

**Files:**
- Create: `dashboard/ui/src/components/Wizard/RunStep/AmberStartForm.tsx`
- Create: `dashboard/ui/src/components/Wizard/RunStep/AmberRunView.tsx`
- Create: `dashboard/ui/src/components/Wizard/RunStep/AmberRunPanel.tsx`

**`AmberStartForm.tsx`:** Form for starting an AMBER job. Fields:
- `binary` — `Select` with `pmemd.cuda` / `pmemd.MPI`
- `np` — numeric `Input` (MPI processes)
- `ntomp` — numeric `Input` (OpenMP threads)
- `ewald` — `Select` with `default` / `optimized`
- `extra_args` — optional text `Input`
- Submit button calls `useSubmitAmber` mutation

**`AmberRunView.tsx`:** Mirror of `RunView.tsx` for AMBER:
- Uses `useAmberStatus` for job polling
- Uses `useAmberLogs` for log display
- `logType` select has only `stdout` and `stderr` (no GMX log)
- Shows `AmberStartForm` when no job exists, `JobStatusDisplay` + logs when job exists

**`AmberRunPanel.tsx`:** Contains `AmberInputSelector` (left column) + `AmberRunView` (right column, shown when all 3 files are selected). Uses `useAmberStatuses` and `useDeleteAmber`.

- [ ] Create all three files
- [ ] Type-check: `npx tsc --noEmit` — the `AmberRunPanel` missing-module error from Task 17 should now resolve
- [ ] Commit: `git commit -m "feat(ui): add AmberRunPanel, AmberRunView, AmberStartForm"`

---

### Task 21: AmberTunePanel + AmberTunerView + AmberTunerTable

**Files:**
- Create: `dashboard/ui/src/components/Wizard/TuneStep/AmberTunerTable.tsx`
- Create: `dashboard/ui/src/components/Wizard/TuneStep/AmberTunerView.tsx`
- Create: `dashboard/ui/src/components/Wizard/TuneStep/AmberTunePanel.tsx`

**`AmberTunerTable.tsx`:** Trial results table showing columns `binary`, `ewald`, `np`, `ntomp`, `performance (ns/day)`. Receives `trials: AmberTunerTrial[]`.

**`AmberTunerView.tsx`:** Mirror of `TunerView.tsx` for AMBER:
- Uses `useRunAmberTuner` (with prmtop/inpcrd/mdin params)
- Uses `useTunerStatus`, `useStopTuner`, `useTunerTrialLogs` (all engine-agnostic, keyed by prmtop name)
- Renders `AmberTunerTable` with trials from the job

**`AmberTunePanel.tsx`:** Contains `AmberInputSelector` (left) + `AmberTunerView` (right, shown when all 3 files selected) + Skip Tuning button. Uses `useDeleteTuner`.

- [ ] Create all three files
- [ ] Type-check: `npx tsc --noEmit` — `AmberTunePanel` missing-module error from Task 18 should now resolve
- [ ] Commit: `git commit -m "feat(ui): add AmberTunePanel, AmberTunerView, AmberTunerTable"`

---

## Phase 7 — Analyze Step Engine Config

### Task 22: Engine-aware Analyze step

**Files:**
- Create: `dashboard/ui/src/components/Wizard/AnalyzeStep/engine-analyze-config.ts`
- Modify: `dashboard/ui/src/components/Wizard/AnalyzeStep/AnalyzeStep.tsx`
- Modify: `dashboard/ui/src/components/Wizard/AnalyzeStep/AnalyzeSidebar.tsx`

**`engine-analyze-config.ts`:**
```typescript
interface AnalyzeConfig {
  structureExts: string[]
  trajectoryExts: string[]
  topologyExts: string[]
  preprocessingTopologyExts: string[]
}

export const ANALYZE_CONFIG: Record<Engine, AnalyzeConfig> = {
  gmx: {
    structureExts: ["pdb", "gro"],
    trajectoryExts: ["xtc", "trr"],
    topologyExts: ["tpr", "top", "prmtop", "psf"],
    preprocessingTopologyExts: ["tpr"],
  },
  amber: {
    structureExts: ["pdb"],
    trajectoryExts: ["nc"],
    topologyExts: ["prmtop", "parm7"],
    preprocessingTopologyExts: [],
  },
}
```

**`AnalyzeStep.tsx`:**
- Import `ANALYZE_CONFIG` and replace the hardcoded `PREPROCESSED_TOPOLOGY_FORMATS` / `PREPROCESSING_TPR_FORMATS` constants with values derived from `ANALYZE_CONFIG[experiment.engine]`
- Pass `structureExts` and `trajectoryExts` from the config into `AnalyzeSidebar` as new props

**`AnalyzeSidebar.tsx`:**
- Add `structureExts: string[]` and `trajectoryExts: string[]` to `AnalyzeSidebarProps`
- Replace the hardcoded `ext={["pdb", "gro"]}` and `ext={["xtc", "trr"]}` on the two `FileSelector` components with the prop values

- [ ] Create `engine-analyze-config.ts`
- [ ] Update `AnalyzeStep.tsx` to use config
- [ ] Update `AnalyzeSidebar.tsx` to accept ext props
- [ ] Type-check: `cd dashboard/ui && npx tsc --noEmit`
  Expected: no errors
- [ ] Run full backend tests one final time: `cd dashboard/api && python -m pytest tests/ -v`
  Expected: all pass
- [ ] Commit: `git commit -m "feat(ui): engine-aware file extensions in AnalyzeStep"`

---

## Post-implementation checklist

- [ ] Verify `make demo` runs without errors (demo harness uses real models/routes)
- [ ] Run `cd dashboard/api && python -m pytest tests/ -v` — all pass
- [ ] Run `cd mdrun-api && python -m pytest tests/ -v` — all pass
- [ ] Run `cd dashboard/ui && npx tsc --noEmit` — zero errors
