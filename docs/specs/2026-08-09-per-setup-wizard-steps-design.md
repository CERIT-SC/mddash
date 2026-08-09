# Per-Setup Wizard Steps — Design

**Date:** 2026-08-09
**Status:** Approved (brainstorming)
**Scope:** Dashboard API (`dashboard/api`) + Dashboard UI (`dashboard/ui`) wizard

## Goal

Each simulation setup (`.simulation.json` manifest) owns its own wizard progress. The setup tabs move above the wizard stepper and wrap the entire per-tab wizard (stepper header + active step). Wizard state (active tab, active step) lives in URL search params (`/$id/wizard?tab=protein&step=2`) instead of component-local state. Step inference remains server-side but is re-scoped from the experiment to the individual manifest. Publishing stays experiment-level. No DB migrations.

## Decisions (locked during brainstorming)

| Decision | Outcome |
|---|---|
| Publish scope | Experiment-level: a shared final step, gated on experiment state; `mdrepo_published` unchanged |
| Step inference location | Server-side on `Simulation`, reusing the existing ladder; UI never computes steps |
| `?tab=` identity | Simulation **name** (human-friendly URLs); names become unique per experiment |
| `?step=` | Integer 0–4 |
| Tabs placement | Above the whole wizard container; switching tabs re-renders stepper header + step content |
| Aggregate experiment step | Unchanged (kept for Home badges and Publish gating) |

## Current state (as-is)

- **Step inference:** `Experiment._step_status` (`dashboard/api/models/experiment.py:394-435`) walks a ladder over *all* the experiment's `simulation_jobs`/`tuner_jobs`, `mdrepo_published`, and `_has_setup_files()` (any valid manifest). It is per-experiment: one finished job on any setup pushes the whole experiment to step 4. Served by `GET /experiments/{id}/step`, polled every 5 s by `useExperimentStep` (`dashboard/ui/src/hooks/use-experiment.ts`).
- **Tab/step state:** both live in `useState` in `WizardStepper` (`dashboard/ui/src/components/Wizard/Stepper.tsx`): `activeStep` initialized from `experiment.step`; `selectedSimulationPath` keyed by path. `nextStep()` is an optimistic `queryClient.setQueryData` poke — no API write.
- **Tabs:** `SimulationTabs` renders *below* the stepper header; switching tabs does not change the step. `null` selection = create mode.
- **Jobs already key by `simulation_path`** (`SimulationJob.simulation_path`, `TunerJob.simulation_path`, `AnalysisJob.simulation_path`) — re-scoping the ladder per manifest requires no schema change.
- **Routing:** TanStack Router, manual tree in `dashboard/ui/src/router.tsx`; no `validateSearch`/`useSearchParams` anywhere yet.

## Backend design

### Shared ladder helper

New module `dashboard/api/models/step_status.py`:

```python
def infer_step(*, simulation_jobs, tuner_jobs, manifest_valid, mdrepo_published) -> tuple[int, str]
```

The decision tree is the existing ladder, verbatim: published (5) → publishing (5) → any FINISHED simulation job (4) → any RUNNING job (3) → any job / any tuner trial with performance (2) → any tuner job (1) → valid manifest (1) → 0.

`Experiment._step_status` becomes a thin call into `infer_step` with all its jobs, `self._has_setup_files()` as `manifest_valid`, and `self.mdrepo_published`. Behavior for Home badges and Publish gating is byte-for-byte unchanged.

### Per-setup progress on `Simulation`

`dashboard/api/models/simulation.py` gains a cached computed property (same `@cached(cache=step_status_cache)` pattern):

```python
@property
def step_status(self) -> tuple[int, str]:
    ...  # infer_step(jobs filtered by (experiment_id, simulation_path), manifest_valid=self.valid, mdrepo_published=None)
```

- Jobs are queried as `SimulationJob` / `TunerJob` rows filtered by `experiment_id=self.experiment_id, simulation_path=self.simulation_path`.
- `manifest_valid` is `self.valid` — the manifest's own schema/role check. `missing_files` does not gate (unchanged policy).
- **`mdrepo_published` is deliberately *not* folded in** — Publish is experiment-level, so the per-setup ladder spans 0–4. Edge: an experiment already in draft/published (experiment step 5) still reports per-setup steps 0–4; the UI renders the experiment-wide Publish state separately.
- `Simulation.to_dict()` gains `step` and `status`. `GET /experiments/{id}/simulations` (list and single) already serialize via `to_dict` — **no new endpoints, no migrations**.

### Name uniqueness

Tab identity is the manifest `name`, so POST/PATCH `/experiments/{id}/simulations` reject a duplicate `name` within the experiment via `ValidationError` (problem-details; token e.g. `urn:mddash:duplicate-simulation-name`, solution "Choose a different name."). Validation code only — the model stays file-backed.

### Cleanup

- `GET /experiments/{id}/step` (`dashboard/api/routes/experiments.py:220`) is wizard-only today — **deleted**, along with its tests.
- Demo seed `dashboard/api/_demo/app.py` gains setups at differing steps so `make demo` shows two mid-flight tabs.

## Frontend design

### URL state

`dashboard/ui/src/router.tsx`: the `/$id/wizard` route gains a `validateSearch`:

```ts
{ tab: string | undefined; step: number | undefined }
```

No defaults baked into the route — the shell resolves missing/invalid values. `tab` references a simulation **name**; the shell resolves it against the loaded list. Reserved sentinel `tab=_new` = create mode (replaces today's `selectedSimulationPath = null`).

### Shell layout (`Stepper.tsx` rewritten)

The tab *is* the wizard — the stepper header is per-tab content:

```
┌─ Wizard page ──────────────────────────────────────────────┐
│  Experiment name card  (experiment-level, stays on top)    │
│  [ protein ] [ ligand ] [ + ]        ← SimulationTabs      │
│ ┌────────────────────────────────────────────────────────┐ │
│ │ ◯ Setup — ◯ Tune — ◯ Run — ● Analyze — ◯ Publish       │ │
│ │ (StepperHeader for THIS tab, gated on this setup)      │ │
│ │ <ActiveStep/>                                          │ │
│ └────────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────┘
```

- `Stepper.tsx` becomes the **shell**: tabs + extracted presentational `StepperHeader` (the existing hand-rolled 5-icon header, with `STEP_ICONS/STEP_LABELS` constants) + step dispatch (`STEP_COMPONENTS`). No `activeStep` / `selectedSimulationPath` local state; no experiment cache mutation.
- **Canonicalization:** `tab` undefined & simulations exist → `navigate(replace)` to `?tab=<first name>&step=<that sim's step>`; `tab` undefined & no simulations → `?tab=_new&step=0`. The URL is canonical after first render.
- **Tab switch:** changing `?tab=` resets `step` to the newly selected setup's own `step` (unless `step` was explicitly pinned in the URL on entry — the pinned value is then clamped by gating).
- **Gating:** steps 0–3 clickable when `idx <= selectedSimulation.step`; step 4 (Publish) clickable per the unchanged experiment-level rule (experiment has reached step ≥ 4). `tab=_new` shows the box with Setup at step 0 and nothing else reachable.
- **Navigation:** `changeStep` / `nextStep` both collapse into `goToStep(n) := navigate({ search: { tab, step: n } })`. The `DEBUG: next step` button stays (navigates to `selected.step + 1`, clamped); in `DEBUG` builds the step-clamp from the Error handling section is skipped so the button still cheats past inference — production clamping is strict.
- **Polling:** the shell calls `useSimulations(id, { refetchInterval: 5000 })` — the wizard's single heartbeat, replacing the deleted `useExperimentStep` one-for-one. Tab badges, stepper gating, and step guards all derive from that one query. The analyze-entry invalidation effect survives as invalidation when `step === 3`.

### Narrowed step contract

```ts
// before — 8 props drilled through every step
experiment, nextStep, changeStep, simulations, simulationsLoading,
selectedSimulation, selectedSimulationPath, setSelectedSimulationPath

// after
interface WizardStepProps {
  experiment: Experiment
  simulation: Simulation | null   // null ⇔ create mode (tab=_new)
  goToStep: (step: number) => void
}
```

- No step manages the simulation list; the shell resolves `?tab=` → `simulation` in one place.
- **Per-step impact:**
  - `SetupStep`: `simulation === null` → empty `SimulationEditor` (create); else edit mode. Keeps details card + `NotebookController`.
  - `TuneStep` / `RunStep` / `AnalyzeStep`: drop the find-by-path plumbing; guard `!simulation` → "create a setup first" prompt linking to `?tab=_new`. Role-gating in `util/simulation.ts` (`simulationUnavailableReason`) is untouched — already per-manifest.
  - `TunerView.goToRunStep` becomes `goToStep(2)`; allowed because the launch already created the job row and the sims poll will report step ≥ 2 (launch hooks already invalidate the simulations query).
  - `PublishStep`: unchanged (experiment-level); may ignore `simulation`.
- **Unchanged:** per-panel job filtering by `simulation_path`, `SimulationTabs` lock/invalid badge icons, Analyze's inner viewer/analysis tab (stays local state, not URL-synced — out of scope).

## Data flow

1. `useSimulations` (5 s poll) is the only wizard heartbeat; list payload carries `step`/`status` per setup.
2. Job/tuner/analysis mutations keep their existing TanStack Query invalidations (including `["experiment", id, "simulations"]`), so the ladder refreshes within one tick.
3. Publishing still mutates `experiment.mdrepo_published` via the existing publish routes; the experiment payload keeps its server-side `step`/`status` for Home and Publish gating.

## Error handling

All repair is shell-level; toasts only where the user just acted (via existing problem-details flow):

- `?tab=` names a simulation that no longer exists → navigate-replace to first tab + its step. No error UI.
- Duplicate name on create/rename → `ValidationError` → toast (`ApiError.message` = solution first).
- `?step=` beyond the selected setup's allowed step → clamped via navigate-replace; stale deep links still land sensibly.
- Successful create on `tab=_new` → navigate to `?tab=<new name>&step=1`.
- Unknown-experiment / routing 404 and the root error boundary: unchanged.

## Testing & verification

- **API (`make test`):** per-setup ladder — two jobs on different `simulation_path`s; assert each simulation's `step`/`status` in the list payload; assert `experiment.step` aggregate unchanged; duplicate-name rejection; remove tests of deleted `/step` endpoint.
- **Types & format:** `make fix`, `make type-check`.
- **Manual (`make demo`, seeded with setups at differing steps):** refresh restores `?tab=&step=`; back/forward walks tabs; direct link to `?tab=ligand&step=2` gates correctly; `+` create flow lands on `?tab=<name>&step=1`; publish state renders regardless of active tab.
- **Docs:** update `dashboard/ui/AGENTS.md` lines describing the wizard ("Wizard step lives in the backend", Stepper optimistic updates) to the URL-driven model.

## Out of scope

- Per-setup publishing / per-simulation MDRepo deposition state.
- URL-syncing Analyze's inner viewer/analysis tab.
- GMX/AMBER panel duplication (`TunerView`/`RunView` twins) — separate cleanup, not entangled with this rework.
