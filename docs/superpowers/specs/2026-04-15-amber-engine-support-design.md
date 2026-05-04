# AMBER Engine Support Design

**Date:** 2026-04-15  
**Status:** Approved  
**Scope:** Add AMBER molecular dynamics engine support alongside GROMACS across the full wizard workflow, designed for easy addition of future MD engines.

---

## Background

The platform currently supports only GROMACS (`gmx`) as its MD engine. The Gromacs Tuner service already exposes AMBER endpoints (`/tuning-jobs/amber`), and an AMBER Docker image (`cerit.io/xkrasa/amber:24`) exists. The MDDB analysis workflow (`mwf`) natively supports AMBER inputs without conversion.

AMBER input files: `.prmtop`/`.parm7` (topology), `.inpcrd`/`.rst7`/`.nc` (coordinates), `.mdin` (run control).  
AMBER run parameters tuned by the tuner: `binary` (`pmemd.cuda` | `pmemd.MPI`), `np`, `ntomp`, `ewald` (`default` | `optimized`).  
MolStar supports: `.prmtop`/`.parm7` as topology, `.nc`/`.nctraj` as trajectory — no conversion needed.  
`mwf` supported formats: topology `.prmtop`, trajectory `.nc`, structure `.pdb` — AMBER data fed directly.

---

## Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Engine selection | Per-experiment, immutable after creation | Simplifies every downstream component |
| Run-step job models | Joined Table Inheritance (`SimulationJob` base + `GromacsJob` + `AmberJob`) | Proper NOT NULL constraints per engine; `Experiment` has ONE `simulation_jobs` relationship that never grows |
| Tuner job model | Single table with `engine` column + nullable AMBER file columns | Already one relationship on `Experiment`; no growth problem |
| MDRun API endpoints | `POST /api/jobs/gmx` + `POST /api/jobs/amber`, shared GET/DELETE | Matches tuner pattern; creation payloads are completely different |
| UI extensibility | Engine-dispatcher pattern at step level | Each engine's UI lives in one focused panel file; adding a 3rd engine = one new file + one map entry |
| AMBER analysis | Full support via `mwf` (engine-agnostic) + MolStar | No new analysis infrastructure needed; sidebar file filters are engine-driven by config |

---

## Architecture

### Engine Enum

New `dashboard/api/enums/engine.py`:
```python
class Engine(str, Enum):
    GMX = "gmx"
    AMBER = "amber"
```

New `AmberBinary` and `EwaldPreset` enums in `dashboard/api/enums/`:
```python
class AmberBinary(str, Enum):
    CUDA = "pmemd.cuda"
    MPI  = "pmemd.MPI"

class EwaldPreset(str, Enum):
    DEFAULT   = "default"
    OPTIMIZED = "optimized"
```

---

### Experiment Model

`Experiment` gains one column:
```python
engine: Mapped[Engine] = mapped_column(db.Enum(Engine), nullable=False, default=Engine.GMX)
```

`ExperimentSchema` replaces `gromacs_jobs` with `simulation_jobs` (polymorphic nested field).  
`Experiment.step` calculation queries `SimulationJob.query.filter_by(experiment_id=id)` to determine run-step completion.

---

### SimulationJob — Joined Table Inheritance

#### Base table: `simulation_jobs`

| Column | Type | Notes |
|--------|------|-------|
| `id` | String(36) PK | UUID from MDRun |
| `experiment_id` | String(5) FK | |
| `created_at` | DateTime | |
| `engine` | Enum(Engine) | JTI discriminator |
| `np` | Integer | MPI processes — common to both |
| `ntomp` | Integer | OpenMP threads — common to both |
| `extra_args` | Text | |
| `_start_timestamp` | Integer nullable | |
| `_finish_timestamp` | Integer nullable | |
| `_nsteps` | Integer nullable | |
| `_performance` | Float nullable | ns/day |
| `_last_known_status` | Enum(JobStatus) nullable | |

Common methods on `SimulationJob`: `status` property (polls MDRun), `delete()`, `estimated_time`, `performance`, `nsteps`, `nsteps_done`, `start_timestamp`, `finish_timestamp`.

#### `gromacs_jobs` table (joined)

| Column | Type |
|--------|------|
| `id` | FK → `simulation_jobs.id` PK |
| `tpr_name` | String(255) NOT NULL |
| `pme` | Enum(DeviceType) NOT NULL |
| `nb` | Enum(DeviceType) NOT NULL |

Engine-specific: log parsing (GROMACS `.log` format), `get_log()` types (`gmx`, `stdout`, `stderr`), `RESULT_EXTENSIONS = ["edr", "gro", "log", "trr", "xtc", "cpt", "fit.xtc"]`.

#### `amber_jobs` table (joined)

| Column | Type |
|--------|------|
| `id` | FK → `simulation_jobs.id` PK |
| `prmtop_name` | String(255) NOT NULL |
| `inpcrd_name` | String(255) NOT NULL |
| `mdin_name` | String(255) NOT NULL |
| `binary` | Enum(AmberBinary) NOT NULL |
| `ewald` | Enum(EwaldPreset) NOT NULL |

Engine-specific: log parsing (AMBER `.out` format for ns/day), `get_log()` types (`stdout`, `stderr`), `RESULT_EXTENSIONS = ["nc", "rst7", "mdinfo", "out"]`.

SQLAlchemy mapping:
```python
class SimulationJob(db.Model):
    __tablename__ = "simulation_jobs"
    __mapper_args__ = {"polymorphic_on": "engine"}

class GromacsJob(SimulationJob):
    __tablename__ = "gromacs_jobs"
    __mapper_args__ = {"polymorphic_identity": Engine.GMX}
    id: Mapped[str] = mapped_column(ForeignKey("simulation_jobs.id"), primary_key=True)

class AmberJob(SimulationJob):
    __tablename__ = "amber_jobs"
    __mapper_args__ = {"polymorphic_identity": Engine.AMBER}
    id: Mapped[str] = mapped_column(ForeignKey("simulation_jobs.id"), primary_key=True)
```

#### Migration strategy

Migration creates `simulation_jobs` base table, copies existing `gromacs_jobs` rows into it (setting `engine='gmx'`, copying `np`, `ntomp`, `extra_args`, status fields), then drops migrated columns from `gromacs_jobs` and adds the FK `id → simulation_jobs.id`. Existing `gromacs_jobs` data is fully preserved; no rows are deleted.

---

### TunerJob Model Changes

`TunerJob` stays as a single table. New columns:

| Column | Type | Notes |
|--------|------|-------|
| `engine` | Enum(Engine) NOT NULL | Default `GMX` for existing rows |
| `inpcrd_name` | String(255) nullable | AMBER only |
| `mdin_name` | String(255) nullable | AMBER only |

`tpr_name` remains the primary input file identifier (stores `.prmtop` path for AMBER jobs — the column name is internal-only and not user-facing).

`TunerJob.start()`, `_status()`, `stop()`, `delete()` each dispatch on `self.engine`:
```python
match self.engine:
    case Engine.GMX:
        tuner.gmx_submit(tpr_path, ...)
    case Engine.AMBER:
        tuner.amber_submit(tpr_path, inpcrd_path, mdin_path, ...)
```

`TunerJob._status()` dispatches to `tuner.amber_poll_status` for AMBER. Preserved trials JSON shape differs per engine (AMBER trials carry `binary`/`ewald`; GMX carry `nb`/`pme`) — both stored in the existing `preserved_trials` JSON column.

---

### Dashboard API Changes

#### New routes: `routes/amber.py` (`amber_bp`)

Mirrors `routes/gmx.py` exactly in structure:

| Method | Path | Notes |
|--------|------|-------|
| GET | `/experiments/<id>/amber` | List `AmberJob` by experiment |
| GET | `/experiments/<id>/amber/<path:prmtop_name>` | Get by prmtop name |
| POST | `/experiments/<id>/amber/<path:prmtop_name>` | Submit job; form fields: `prmtop_name`, `inpcrd_name`, `mdin_name`, `binary`, `np`, `ntomp`, `ewald`, `extra_args` |
| DELETE | `/experiments/<id>/amber/<path:prmtop_name>` | Delete job |
| GET | `/experiments/<id>/amber/<path:prmtop_name>/log` | Log; types: `stdout`, `stderr` |

#### Updated `routes/experiments.py`

`create_experiment` accepts new `engine` form field (default `gmx`). Engine stored on `Experiment` at creation, never updated.

#### Updated `routes/tuner.py`

`start_tuner_job` accepts additional query params `inpcrd_name` and `mdin_name` (required when engine is AMBER, ignored for GMX).

Trial log routes dispatch to `tuner.amber_get_trial_stdout/stderr` vs `tuner.gmx_get_trial_stdout/stderr` based on job engine.

#### New schemas

- `SimulationJobSchema` — polymorphic base; marshmallow-sqlalchemy resolves to `GromacsJobSchema` or `AmberJobSchema` based on `engine`
- `AmberJobSchema` — auto-schema for `AmberJob`

#### Updated `clients/mdrun.py`

New `create_amber_job(experiment_id, prmtop_name, inpcrd_name, mdin_name, bucket_name, binary, np, ntomp, ewald, extra_args)` hitting `POST /api/jobs/amber`.

Existing `create_job(...)` updated to hit renamed `POST /api/jobs/gmx`.

---

### MDRun API Changes

#### Endpoint restructure

| Before | After | Notes |
|--------|-------|-------|
| `POST /api/jobs` | `POST /api/jobs/gmx` | Different payload per engine |
| — | `POST /api/jobs/amber` | New |
| `GET /api/jobs/{id}` | `GET /api/jobs/gmx/{id}` + `GET /api/jobs/amber/{id}` | Same handler, separate routes |
| `DELETE /api/jobs/{id}` | `DELETE /api/jobs/gmx/{id}` + `DELETE /api/jobs/amber/{id}` | Same handler, separate routes |

GET and DELETE routes per engine point to shared internal functions — the implementation is identical since `MdrunJob` is engine-agnostic. Separate routes match the tuner pattern and keep the API self-consistent:

```python
def _get_job(job_id): ...
def _delete_job(job_id): ...

@gmx_bp.route("/<job_id>", methods=["GET"])
def get_gmx_job(job_id): return _get_job(job_id)

@amber_bp.route("/<job_id>", methods=["GET"])
def get_amber_job(job_id): return _get_job(job_id)
```

`MdrunJob` model: no changes needed.

The dashboard API client `clients/mdrun.py` gains `get_gmx_job(id)` / `get_amber_job(id)` and `delete_gmx_job(id)` / `delete_amber_job(id)` (internally identical, different URLs). `SimulationJob.status` in the dashboard API dispatches to the right client function via `self.engine`.

#### New `GmxJobCreateRequestSchema` and `AmberJobCreateRequestSchema`

`AmberJobCreateRequestSchema` fields: `experiment_id`, `prmtop_name`, `inpcrd_name`, `mdin_name`, `bucket_name`, `binary`, `np`, `ntomp`, `ewald`, `extra_args`.

#### New `k8s_client.create_amber_job()`

Same structure as `create_gromacs_job()`:
- S3 init container downloads `prmtop`, `inpcrd`, `mdin` files from S3
- Main container image: `cerit.io/xkrasa/amber:24`
- Command: `pmemd.cuda ...` or `mpirun -np {np} pmemd.MPI ...` depending on `binary`
- S3 sync sidecar uploads results (`.nc`, `.rst7`, `.mdinfo`, `.out`)
- Same security context (non-root UID 1000), same resource pattern

---

## UI Architecture

### Engine type

`src/util/const.ts`:
```typescript
export const Engine = { GMX: "gmx", AMBER: "amber" } as const
export type Engine = typeof Engine[keyof typeof Engine]
```

### Types

`src/util/types.ts`:
- `Experiment.simulation_jobs: SimulationJob[]` replaces `gromacs_jobs`
- `SimulationJob = GromacsJob | AmberJob` (discriminated union on `engine`)
- `AmberJob`: `prmtop_name`, `inpcrd_name`, `mdin_name`, `binary: AmberBinary`, `np`, `ntomp`, `ewald: EwaldPreset`, plus shared status/perf fields
- `AmberTunerTrial`: `binary: AmberBinary`, `np`, `ntomp`, `ewald: EwaldPreset`, `performance`
- `TunerJob` gains `engine: Engine`; `trials` typed as `GmxTunerTrial[] | AmberTunerTrial[]`

### Dispatcher pattern

```typescript
const ENGINE_PANELS = {
  gmx:   GmxRunPanel,
  amber: AmberRunPanel,
} satisfies Record<Engine, ComponentType<WizardStepProps>>

const RunStep = (props: WizardStepProps) => {
  const Panel = ENGINE_PANELS[props.experiment.engine]
  return <Panel {...props} />
}
```

Same pattern for `TuneStep`.

### New experiment page

`pages/New.tsx` adds an engine selector (segmented control: `GROMACS` / `AMBER`) above the Initial Data section. Defaults to `GROMACS`. Engine sent as `engine` field in FormData.

### Wizard step changes

#### Setup (unchanged)
Engine-agnostic. No changes.

#### Tune

`TuneStep.tsx` → becomes dispatcher.

`GmxTunePanel.tsx` (extracted from current `TuneStep.tsx`):
- `TprSelector` for `.tpr` files
- `TunerView` / `TunerTable` showing `nb`, `pme`, `np`, `ntomp` columns
- Uses existing `useTunerStatuses`, `useRunTuner`, `useStopTuner`, `useDeleteTuner`

`AmberTunePanel.tsx` (new):
- `AmberInputSelector` for 3 files (prmtop, inpcrd, mdin)
- `AmberTunerView` / `AmberTunerTable` showing `binary`, `ewald`, `np`, `ntomp` columns
- New `useRunAmberTuner` mutation (sends all 3 file names as query params)

#### Run

`RunStep.tsx` → becomes dispatcher.

`GmxRunPanel.tsx` (extracted from current `RunStep.tsx` + `RunView.tsx`):
- `TprSelector` for `.tpr` files
- `RunView` with `StartForm` (np/ntomp/nb/pme + mdrun arg builder)
- `JobStatusDisplay`, `LogsView` (log types: gmx, stdout, stderr)
- Uses existing `useGromacsStatuses`, `useSubmitGmx`, `useDeleteGmx`, `useGromacsLogs`

`AmberRunPanel.tsx` (new):
- `AmberInputSelector` for prmtop/inpcrd/mdin files
- `AmberRunView` with `AmberStartForm` (binary selector, np, ntomp, ewald, extra_args for pmemd)
- `JobStatusDisplay` reused, `LogsView` reused (log types: stdout, stderr only)
- New hooks: `useAmberStatuses`, `useSubmitAmber`, `useDeleteAmber`, `useAmberLogs`

#### Analyze

`AnalyzeStep.tsx` reads engine-specific config:

```typescript
const ANALYZE_CONFIG: Record<Engine, AnalyzeConfig> = {
  gmx: {
    structureExts:             ["pdb", "gro"],
    trajectoryExts:            ["xtc", "trr"],
    topologyExts:              ["tpr", "top", "prmtop", "psf"],
    preprocessingTopologyExts: ["tpr"],
  },
  amber: {
    structureExts:             ["pdb"],
    trajectoryExts:            ["nc"],
    topologyExts:              ["prmtop", "parm7"],
    preprocessingTopologyExts: [],   // no TPR-equivalent preprocessing for AMBER
  },
}
```

MolStar already handles `prmtop` + `nc` natively — viewer unchanged. `mwf` is engine-agnostic — analysis backend unchanged.

#### Publish (unchanged)
File-upload-based, engine-agnostic. No changes.

### New hooks

`src/hooks/use-amber.ts`:
- `useAmberStatuses(experimentId)` → `GET /experiments/{id}/amber`
- `useAmberStatus(experimentId, prmtopName)` → `GET /experiments/{id}/amber/{name}` with 5s polling
- `useSubmitAmber(experimentId)` → `POST /experiments/{id}/amber/{name}`
- `useDeleteAmber(experimentId)` → `DELETE /experiments/{id}/amber/{name}`
- `useAmberLogs(experimentId, prmtopName, logType, shouldPoll)` → `GET .../log`

`src/hooks/use-tuner.ts` extended:
- `useRunAmberTuner(experimentId)` — sends `prmtop_name`, `inpcrd_name`, `mdin_name` as query params

---

## File Inventory

### New files
| File | Purpose |
|------|---------|
| `dashboard/api/enums/engine.py` | `Engine`, `AmberBinary`, `EwaldPreset` enums |
| `dashboard/api/models/amber_job.py` | `AmberJob` JTI subclass |
| `dashboard/api/models/simulation_job.py` | `SimulationJob` JTI base |
| `dashboard/api/routes/amber.py` | `amber_bp` blueprint |
| `dashboard/api/schemas/amber_job.py` | `AmberJobSchema` |
| `dashboard/api/schemas/simulation_job.py` | Polymorphic `SimulationJobSchema` |
| `dashboard/api/migrations/versions/003_amber_engine.py` | Migration |
| `dashboard/ui/src/hooks/use-amber.ts` | AMBER job hooks |
| `dashboard/ui/src/components/Wizard/RunStep/GmxRunPanel.tsx` | Extracted GMX run panel |
| `dashboard/ui/src/components/Wizard/RunStep/AmberRunPanel.tsx` | New AMBER run panel |
| `dashboard/ui/src/components/Wizard/RunStep/AmberRunView.tsx` | AMBER run view |
| `dashboard/ui/src/components/Wizard/RunStep/AmberStartForm.tsx` | AMBER start form |
| `dashboard/ui/src/components/Wizard/TuneStep/GmxTunePanel.tsx` | Extracted GMX tune panel |
| `dashboard/ui/src/components/Wizard/TuneStep/AmberTunePanel.tsx` | New AMBER tune panel |
| `dashboard/ui/src/components/Wizard/TuneStep/AmberTunerView.tsx` | AMBER tuner view |
| `dashboard/ui/src/components/Wizard/TuneStep/AmberTunerTable.tsx` | AMBER trial table |
| `dashboard/ui/src/components/Wizard/AmberInputSelector.tsx` | 3-file input selector for AMBER |
| `dashboard/ui/src/components/Wizard/AnalyzeStep/engine-analyze-config.ts` | Engine → file extension config |

### Modified files
| File | Change |
|------|--------|
| `dashboard/api/enums/__init__.py` | Export new enums |
| `dashboard/api/models/__init__.py` | Export new models |
| `dashboard/api/models/experiment.py` | Add `engine` column; `simulation_jobs` relationship replaces `gromacs_jobs` |
| `dashboard/api/models/gromacs_job.py` | Refactor as `GromacsJob(SimulationJob)` JTI subclass |
| `dashboard/api/models/tuner_job.py` | Add `engine`, `inpcrd_name`, `mdin_name`; dispatch in start/status/stop/delete |
| `dashboard/api/routes/__init__.py` | Register `amber_bp` |
| `dashboard/api/routes/experiments.py` | Accept `engine` field on creation |
| `dashboard/api/routes/tuner.py` | Accept AMBER params; dispatch trial log routes |
| `dashboard/api/schemas/__init__.py` | Export new schemas |
| `dashboard/api/schemas/experiment.py` | Replace `gromacs_jobs` with `simulation_jobs` |
| `dashboard/api/clients/mdrun.py` | Add `create_amber_job()`, `get_gmx_job()`, `get_amber_job()`, `delete_gmx_job()`, `delete_amber_job()`; update `create_job()` URL to `/gmx`; update `get_job()`/`delete_job()` URLs |
| `mdrun-api/routes.py` | Rename `POST /api/jobs` → `POST /api/jobs/gmx`; add `POST /api/jobs/amber`; split `GET`/`DELETE` into per-engine routes backed by shared handlers |
| `mdrun-api/schemas.py` | Rename `JobCreateRequestSchema` → `GmxJobCreateRequestSchema`; add `AmberJobCreateRequestSchema` |
| `mdrun-api/k8s_client.py` | Add `create_amber_job()` |
| `dashboard/ui/src/util/types.ts` | Add `Engine`, `AmberJob`, `AmberTunerTrial`; update `Experiment`, `TunerJob` |
| `dashboard/ui/src/util/const.ts` | Add `Engine` constant |
| `dashboard/ui/src/hooks/use-tuner.ts` | Add `useRunAmberTuner` |
| `dashboard/ui/src/components/Wizard/Stepper.tsx` | No change to step array; dispatcher components slot in transparently |
| `dashboard/ui/src/components/Wizard/RunStep/RunStep.tsx` | Becomes engine dispatcher |
| `dashboard/ui/src/components/Wizard/RunStep/RunView.tsx` | Stays as-is; nested inside new `GmxRunPanel.tsx` |
| `dashboard/ui/src/components/Wizard/RunStep/StartForm.tsx` | Renamed to `GmxStartForm.tsx` |
| `dashboard/ui/src/components/Wizard/TuneStep/TuneStep.tsx` | Becomes engine dispatcher |
| `dashboard/ui/src/components/Wizard/TuneStep/TunerView.tsx` | Extracted into `GmxTunePanel` |
| `dashboard/ui/src/components/Wizard/TuneStep/TunerTable.tsx` | Stays as `GmxTunerTable` |
| `dashboard/ui/src/components/Wizard/AnalyzeStep/AnalyzeStep.tsx` | Read engine config for file filters |
| `dashboard/ui/src/components/Wizard/AnalyzeStep/AnalyzeSidebar.tsx` | Accept `structureExts`, `trajectoryExts` as props |
| `dashboard/ui/src/pages/New.tsx` | Add engine selector |
| `dashboard/ui/CLAUDE.md` | Update supported formats list (add prmtop/parm7, nc/nctraj) |
