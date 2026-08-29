# The Experiment Wizard: Steps, Stepper, and Simulations

The wizard (`/dash/experiments/<id>`, route `/experiments/<id>`) is the main working view of an experiment. This guide explains the mechanics common to all five steps; per-step details are in separate guides.

## Page structure

1. **Title row** — a fixed "Experiment" heading followed by a chip button showing the experiment's name with a pencil icon (aria-label "Rename experiment"). Clicking it opens a **"Rename experiment"** dialog with a Name field and **Cancel** / **Save** buttons ("Experiment renamed" toast on success). The same row carries the experiment's metadata, separated by dividers: the **source** (e.g. "RCSB PDB (1LYZ)" — opens an "Experiment source" dialog with structure metadata and downloads; "Uploaded N files" — opens an "Uploaded files" dialog with download links; or a repository link), the **creation date**, and the **notebooks repository** (shortened, links out). Renaming is also available from the Home page card menu.
2. **Simulation tabs** — one tab per simulation defined in the experiment, plus a **"New simulation"** button to the right (see below).
3. **Step card** — a bordered card containing the **stepper** (Setup → Tune → Run → Analyze → Publish) and the active step's panel below it.

## URL state

The wizard's view state lives in the URL and survives bookmarks and refreshes:

- `?simulation=<name>` — the selected simulation tab (`_new` is the creation view).
- `?step=<0–4>` — the open wizard step; defaults to the simulation's server-reported progress.
- `?source=manual` — the Setup step's "Manual" tab.
- `?trial=<id>` — the tuning trial picked on the Tune step.
- `?mode=manual` — the Tune step's "Manual configuration" view.

## How steps unlock

The wizard does not have a "Next" button. Progress is computed on the server from what exists in the experiment, and the frontend polls it every 5 seconds (pausing when nothing is live):

| Step | Unlocks when |
|---|---|
| Setup → Tune | at least one valid simulation manifest (`.simulation.json`) exists for the experiment |
| Tune → Run | a tuning trial finished with measured performance — **or** the user submitted a manual configuration on the Tune step |
| Run → Analyze | a simulation job exists (Analyze is reachable even while the job is still RUNNING) |
| Analyze → Publish | experiment-level: a simulation job has FINISHED **or** an MDRepo draft/published record exists |

Publish is an experiment-level step, not the end of a single simulation's ladder: once unlocked, it is clickable regardless of which simulation tab is selected.

Stepper visuals: the active step is a highlighted circle showing its icon (Atom, SlidersHorizontal, Play, ChartColumn, Upload); completed steps are green circles with a check mark; future (locked) steps are grey and disabled. While a production run is in progress, the **Run** marker gains a green **progress ring** with a percentage label (e.g. "Run · 20%"). Clicking a step icon jumps to it — but only up to the highest unlocked step. Going *backwards* is always allowed.

## Simulation tabs and multi-simulation experiments

An experiment can contain several simulations (e.g. replicated runs or different setups of the same system). The tab bar above the step card lists them:

- Each tab shows the simulation **name**.
- Every tab has an **⋯ "Actions for \<name\>"** menu whose only action is **"Delete"** — deleting asks `Delete simulation "<name>"?` ("This permanently removes the simulation manifest and all related jobs. This can't be undone.") and removes the manifest plus its tuner, simulation, and analysis jobs. Whether a simulation is *locked* or *invalid* is shown in the Setup step's form header (see "Step 1: Setup"), not on the tab.
- **"New simulation"** — a link-style button with a plus icon that switches to an unnamed creation tab and jumps to the Setup step to create another simulation. While creating, only Setup is available.

Without an explicit `?simulation=`, the wizard selects the experiment's most recently active simulation (its `latest_simulation_path`), falling back to the first in the list. The selected tab determines which simulation the Tune, Run, and Analyze steps act on.

## Cross-step behavior to remember

- Wizard state is server-side, overlaid with URL state: refreshing the page or logging back in later returns to the same experiment state, and the URL preserves the exact step/tab view.
- Jobs started in any step keep running in the background even if the user navigates away or stops the server.
- Tuning is optional — the Tune step offers a **"Manual configuration"** tab for submitting a run directly with hand-picked parameters (see "Step 2: Tune").
- Deleting a simulation cascade-deletes its tuner, simulation, and analysis jobs (explicit confirmation required).
- Load failures show a durable error alert (with the problem code and a Retry button), not a toast.
