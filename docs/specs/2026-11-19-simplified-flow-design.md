# Simplified flow, design

Date is 2026-11-19.
Status is Approved.
Scope is Dashboard API (`dashboard/api`), Dashboard UI (`dashboard/ui`) and the notebook image (`notebook/`).
Issue is #191. The prototype is https://vaclavklem.github.io/mddash-prototype/.

## Goal

Users run setup from MDDash without opening the notebook, watch its progress, start the simulation with the resources the notebook suggests, and follow every step on one page. The notebook, the tuner and manual resources stay available as expert paths.

## Terminology

#190 (approved) aligns the hierarchy with BioSim CZ and renames it. This spec uses today's code names:

| Today (code, UI) | After #190 | Meaning |
|---|---|---|
| Experiment | Study | Input data, MD engine, protocol repo |
| Simulation (`.simulation.json` manifest, wizard tab) | Experiment | One setup and one simulation run |
| Run (`SimulationJob`) | Simulation | The MD run |

Everything below is per simulation (tab) unless marked experiment-level, so it carries over to #190 experiments unchanged.

## Decisions

| Decision | Outcome |
|---|---|
| Steps | Setup, Configuration, Simulation, Analysis. Tune stops being a step; tuning becomes an option inside Configuration. |
| Step order and counts | One API enum `Step`, declared in display order. The UI takes order, count and last step from it. No literal `3`, `4` or `5`. |
| Layout | The four steps stack as cards on one page. A toggle under the cards switches between full width and a side column with the notebook and files; each browser remembers the choice. The prototype's other footer variants are out of scope. |
| Setup | **Run setup** executes the setup notebook headless as a Kubernetes Job. Opening the notebook stays the way to edit or fix it. |
| Setup progress | Spinner plus "Step k of n · title" and a thin progress bar. n comes from the pipeline tracker's step discovery. |
| Setup resources | Default notebook size, no GPU. Today's size and GPU selection (`NotebookLauncher`) moves behind **Expert…**. |
| Run resources | Defaults come from a new optional manifest field `resources`. **Tune first** runs today's tuner. **Expert…** opens today's manual hardware form. |
| Analysis, Publish | Content unchanged (#192 and later work). Publish stays experiment-level; its button moves to the title row and opens today's Publish UI in a dialog. |
| Setup changes after a run | #190 owns this: changing the setup of a running or finished simulation warns and offers to stop the run and delete its results. Keeping them means copying the experiment instead (#163). Until then the manifest lock works as today. |

## Current state

- `features/experiment/wizard.tsx` renders a five-step stepper (Setup, Tune, Run, Analyze, Publish), one step at a time, selected by `?step=<int>`.
- The ladder is integers. `Simulation._compute_step_status` (`modules/simulations/manifest.py:342`) returns 0–3 and `SimulationSchema.step` is `Field(ge=0, le=3)` (`modules/simulations/schemas.py:47`). The experiment adds publish as 4 (`modules/experiments/models.py:193`), and archiving stores the value in `experiments.archived_step`. The UI hardcodes `PUBLISH_STEP = 4` (`features/experiment/stepper-header.tsx:6`) and `aria-valuemax={5}` (`features/dashboard/experiment-card.tsx:455`).
- Setup: the user starts the notebook pod, opens JupyterLab and clicks ▶ Run Pipeline. The pipeline tracker runs `notebook:run-all-cells` in the browser (`notebook/jupyterlab-pipeline-tracker/src/session.ts:135`). MDDash only polls for the manifest.
- Tune has two tabs, Tuning and Manual configuration, and submits the run (`features/tune/tune-step.tsx`).
- The manifest holds `name`, `engine`, `files` and `extra_args`. Both schemas set `additionalProperties: false`.
- Analysis, upload and archive already run as Kubernetes Jobs on the shared PVC, reconciled on each request (`K8sClient.create_job`, `core/worker_jobs.py`).

## Step ladder

`core/enums.py` gains `Step(StrEnum)`: `setup`, `configuration`, `simulation`, `analysis`. Member order is display order.

`Simulation.step` returns the furthest step the user can open. `status` keeps naming the activity:

| Condition | `step` | `status` |
|---|---|---|
| Run with saved frames, finished or stopped | analysis | simulating, analyzing |
| Run without frames | simulation | simulating |
| Tuner job | configuration | tuning |
| Valid manifest | configuration | setup complete |
| Otherwise | setup | setup |

Today's "trials with performance unlock Run" rung goes away, because Configuration starts the run itself.

Experiment level: `step` is the latest simulation's step. Publishing and published keep `step` at analysis and report in `status` (`publishing`, `published`), not as a fifth rung. A migration converts `experiments.archived_step` to `Step` (0→setup, 1→configuration, 2→simulation, 3 and 4→analysis; `archived_status` already records `published`) and writes member names, per the `db.Enum` gotcha.

`step` becomes the enum in `SimulationSchema` and `ExperimentSchema`. `make openapi` regenerates the UI type, whose value order drives the cards and the dashboard card's segments and "k of n".

## Page layout

- Title row: today's `TitleRow` plus a **Publish…** button, disabled with today's reason until `can_publish`. It opens today's `PublishStep` in a dialog whose open state lives in the URL (`?publish`), so the MDRepo OAuth `return_url` reopens it.
- `SimulationTabs` stay above the cards.
- Cards come from one `STEPS` array keyed by `Step` (label, card config). A card is current (the step being worked on, expanded), open (reachable while an earlier card is still current, e.g. Analysis during a live run), done (Setup and Configuration fold to one summary line with a Show toggle; Simulation and Analysis stay expanded) or locked (dashed, lock icon, reason such as "Available once the setup finishes").
- Simulation hosts today's `RunStep` content and Analysis today's `AnalyzeStep`, minus their Back/Next buttons.
- The Analysis card's Mol* viewer mounts once the card scrolls near view. Rendered off-screen it loads its bundle and a WebGL context on every page visit.
- `?step` is dropped. `validateSearch` ignores old values, so old links still open. `?trial` stays. `?mode=manual` now means the Expert dialog is open.
- The stepper (`WizardStepperHeader`, `shared/ui/stepper.tsx`) is deleted if nothing else uses it.

## Layout toggle

A segmented control under the cards (the prototype's footer) switches between two layouts. The choice lives in `localStorage` like the theme (`app/site-header.tsx`), is read defensively, and defaults to full width.

| | Full width | Side column |
|---|---|---|
| Notebook controls | Today's top bar (`NotebookStatusBar` in `app/app-shell.tsx`) | A Notebook card at the top of the column (status, Start, Open, Stop). The top bar hides, so the page keeps one set of controls. |
| Files | None | A Files panel under the Notebook card |
| Cards | Full width | Right of a sticky column about 320 px wide |

- `SimulationTabs` span both columns, because the Files panel follows the selected simulation.
- Below the `lg` breakpoint the column stacks above the cards and stops being sticky.
- The Files panel groups the selected simulation's files into Input, Notebooks, Setup, Simulation and Analysis. Each file is a download link with its size. A group shows "Updating" while its producer runs (setup run, simulation run, analysis job). An empty group says when it fills, for example "Appears when the simulation starts".
- The API owns the grouping, since it already knows the source files, manifest roles, run outputs and analysis output dirs. `GET /experiments/{id}/file-groups?simulation=<path>` returns `[{category, files}]`. `FileCategory` is an enum declared in display order, and `files` keep today's `FileInfo` shape. Without `simulation` (the create tab) it returns Input and Notebooks only. The panel polls while anything is live.
- The panel is a curated view, not a file browser. Intermediate files such as `temp/` stay reachable in JupyterLab.
- The panel header has **Download all** with the total size (the sum of the listed sizes), so a multi-GB trajectory is visible before the click. It is a plain link to the zip below.

### Download all

`GET /experiments/{id}/file-groups.zip?simulation=<path>` returns the same selection as `file-groups`, so one listing decides both.

- Entries keep their experiment-relative paths, so manifest-relative references still resolve after unzipping.
- The archive streams: entries are stored uncompressed (trajectories are already compressed) with ZIP64, read in chunks in a worker thread, and never staged on disk or in memory.
- `Content-Disposition: attachment` names it after the experiment and simulation, with an ASCII fallback and RFC 5987 `filename*`.
- Files being written, such as a live run's trajectory, are included as they are at that moment.
- Validation errors are problem details before streaming starts. A file that vanishes mid-stream ends the response early and is logged, because headers are already sent.

## Setup card

| State | Shows | Actions |
|---|---|---|
| Not run | "Prepares the system with the workflow's defaults." | **Run setup**, Edit in notebook, Expert… (size, GPU) |
| Starting | Spinner, "Starting setup", or "Waiting for resources" while unschedulable | View notebook, Stop |
| Running | Spinner, "Step 6 of 11 · Solvate", progress bar | View notebook, Stop |
| Failed | Alert "Setup stopped at step 4 of 11 · Parse the input" with the notebook's own error message | Fix in notebook, Show log, Run setup |
| Stopped | Neutral note with the step reached | Run setup, Fix in notebook |
| Done | Summary from the manifest (name, role files) | View in notebook; Run setup again while the simulation has no tuner or run job |
| Edited in notebook (`?source=notebook`) | Today's guide, shortened: run it there, MDDash continues when the manifest appears | Open notebook |

- Workflows without `setup.ipynb` (custom repositories) keep today's guide without **Run setup**.
- The Manual source (a hand-written manifest) stays as a link in the card.
- In the legacy layout one notebook feeds every simulation, so a headless run rewrites the manifest it wrote last time. The create tab therefore offers **Run setup** only while the experiment has no simulation. Another simulation needs a parameter change in the notebook, as today. #190's per-experiment copies lift this.

## Headless setup run

### Where it runs

| | Kubernetes Job (recommended) | Inside the notebook pod |
|---|---|---|
| Survives a closed browser and pod idle culling | Yes | Only while the pod lives, and idle culling must be held off |
| Counts toward the notebook limit (`NS_MAX_NOTEBOOKS`) | No | Yes, Run setup has to start the pod |
| Parity with JupyterLab | Same image, with Binder activation and OMP handling shared through one script | Exact |
| New pieces | Executor CLI, Job, status doc | Server extension, API calls into the pod with the notebook token |
| Existing pattern | Analysis, upload and archive Jobs | None |

Recommended: the Job. Every other long-running computation in MDDash already runs as a reconciled Job, and setup (minimisation, NVT, NPT) can outlive a browser tab or the pod's idle timeout.

### Executor (notebook image)

The pipeline-tracker Python package ships `mddash-run-notebook <notebook> --status <doc>`. It:

- Activates the Binder env and unsets `OMP_NUM_THREADS` on GPU nodes through one script that `start-with-binder.sh` and `run-notebook.sh` also call, so neither rule is copied.
- Finds steps with a Python port of `discovery.ts`. The five `test-notebooks/` pin the expected step lists for both implementations.
- Executes with nbclient (a dependency of the package) in the notebook's directory, saving outputs into the notebook after every cell, so JupyterLab later shows where it stopped.
- Writes a hidden status doc next to the notebook atomically on every step change: `state`, `step`, `total`, `title`, `started_at`, `finished_at`, `manifests` written during the run, and `error` (`step`, `cell`, `ename`, truncated `evalue`).
- Exits non-zero on a cell error.

### API (`modules/setup/`)

- `POST /experiments/{id}/setup` takes `notebook` (default: the root `setup.ipynb`, the same role file the UI opens), plus optional `tier` and `gpu`. The Job name is derived from the experiment and notebook path, so a second start while one runs gets 409. It uses `NOTEBOOK_IMAGE` and the notebook resources scaled by tier (`modules/notebooks/tiers.py`), after `check_quota_headroom`.
- `GET /experiments/{id}/setup` returns the run state with `step`, `total`, `title`, `error` and `manifests`:
  - `starting`: Job pending, no doc yet. Flagged `waiting` while the pod is unschedulable.
  - `running`: the doc reports progress.
  - `done`: Job succeeded and a valid manifest was written.
  - `stopped`: stopped through the API.
  - `failed`: the doc reports an error, the Job failed, the Job vanished while the doc says running ("interrupted"), or the run ended without a valid manifest ("Setup finished without writing a simulation manifest").
- `DELETE /experiments/{id}/setup` stops the run: it deletes the Job and marks the doc stopped.
- No DB table. The Job is the liveness signal and the status doc the durable record. The doc is excluded from S3 sync like the other worker docs (`dashboard/rclone-filters.txt`).
- The notebook's `ename: evalue` is the user's own notebook output and is shown as is. Executor and infrastructure failures (OOMKilled, image pull, a pod that never starts) appear as a friendly `error` with a `solution`, never tracebacks. Start failures (quota, 409) are problem details on the POST.
- Edits saved in JupyterLab during a run are overwritten by the executor's next save. The card says so next to View notebook.

#190 fit: the `notebook` path keeps the executor layout-agnostic. Legacy experiments run the root `setup.ipynb`, #190 experiments run their own copy.

## Configuration card

- Both manifest schemas gain optional `resources` with the engine's run-request shape: GROMACS `np`, `ntomp`, `pme`, `nb`; AMBER `np`, `ntomp`, `binary`, `ewald`. Validation matches `GromacsJobRequest` and `AmberJobRequest`. `extra_args` already carries flags such as `-plumed myplumed.dat`.
- The field is optional, so existing manifests stay valid. Because of `additionalProperties: false`, the schema change must ship before any notebook writes the field.
- The simulation response gains `default_resources`: the parsed `resources`, or null.
- Actions:
  - **Start with default**, primary when defaults exist, submits the run with them. Today's re-run confirmation still applies.
  - **Tune first**, primary when there are no defaults, shows today's tuning view inline (step count, trials table, customise, start).
  - **Expert…** opens today's `HardwareConfigForm` in a dialog.
- Done: one line with the configuration used (ranks × threads, GPU offload).

## Errors

Every failure is a durable alert in its card, never only a toast. Setup failures offer Fix in notebook and Run setup. Infrastructure failures show the API's `solution`.

## Testing

- API: each ladder row, the `archived_step` migration, the setup service (start, 409, quota, every state including interrupted, error mapping), `resources` validation and `default_resources`, file groups (each category, the `simulation` filter, the create tab), the zip (entries and paths match the groups, headers, problem details before streaming), the contract test after `make openapi`.
- Executor: discovery parity on the five test notebooks, status doc transitions, outputs saved on failure.
- UI: Setup card states, Configuration with and without defaults, counts derived from `Step`, the Publish dialog reopening from the URL, the layout toggle (default, remembered choice, exactly one set of notebook controls).
- Demo and e2e: a fake setup Job advancing through steps. Run setup → start with default → finished; setup failure → Fix in notebook.

## Rollout

- API contract changes (`step` enum, setup endpoints, `default_resources`, file groups and their zip) regenerate `openapi.yaml` and the UI client.
- The executor needs a notebook image rebuild.
- `mddash-notebooks` writes `resources` only after the API schema accepts it.

## Out of scope

The rename, per-experiment notebook copies and the setup lock (#190); copying an experiment (#163); the analysis redesign (#192); a Publish redesign; the prototype's embedded-notebook layout and its simulations/replicas variants; a parameter form for setup.

## Open questions

1. Job or notebook pod for the headless run (recommended: Job).
2. Default setup resources. Default size without GPU matches today's notebook default; GPU equilibration would need a GPU default.
3. Publish in a dialog, or a full-width view in its place.
