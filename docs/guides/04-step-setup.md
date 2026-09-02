# Wizard Step 1: Setup

The Setup step (step 0) is where input data becomes a runnable simulation definition. Goal: end up with at least one valid **simulation manifest** (`.simulation.json`) — either produced by the setup notebook or created manually in the editor.

## Page layout

- A **"Set up your simulation"** heading with the subtitle: *"Run the setup notebook to generate a simulation manifest, or create one manually. At least one valid setup is required to continue."*
- **Setup source tabs** — **"From Notebook"** (default) and **"Manual"**; the choice is kept in the URL (`?source=manual`).
- The **simulation form** card ("New simulation" when creating, "Simulation" when editing) — available on both tabs once a simulation is selected/being created.
- While a notebook is running, a **notebook status bar** appears under the site header (on every experiment page) with **"Open notebook"** / **"Stop notebook"** controls.

## Using the setup notebook (guided path)

The **"From Notebook"** tab shows a **"Step by step"** guide box whose three numbered steps light up as their outcomes are met:

1. **"Start the notebook"** — pick a **Size** from the offered tiers (each option is shown as its resources, e.g. `5 cores / 8 GB`), optionally tick the **GPU** checkbox, then click **"Start notebook"**. The notebook status bar then tracks the states: **"Starting…"** → **"Initializing…"** (the environment is being prepared; after repeated probe failures it reads "Taking longer than expected") → a live **uptime** readout once ready.
2. **"▶ Run Pipeline" in the notebook** — click **"Open notebook"**; JupyterLab opens in a new tab with the **setup.ipynb** notebook already loaded (a deep link into the experiment directory). Run the pipeline cells — it fetches/builds the system (from the PDB, repository, or uploaded data), prepares engine input files, and writes a `*.simulation.json` manifest into the experiment directory. **"Stop notebook"** stays available the whole time (disabled only while a stop is in flight or status is unknown).
3. **"Go to Tune"** — the new manifest is detected automatically: the wizard announces `Simulation "<name>" created by the pipeline`, adopts it as the selected tab, and unlocks the Tune step within ~5 seconds.

Completed guide steps get a green check and strikethrough titles.

## Creating a simulation manually (editor path)

The **"Manual"** tab also offers the notebook launcher under a **"Start the notebook"** heading, plus the simulation form. The form card is titled **"New simulation"** when creating and **"Simulation"** when editing; its header shows the engine badge plus **"Locked"**, and **"Valid"** / **"Invalid"** badges when editing. Fields:

- **Name** — placeholder "Enter name of your choice" (create only); description "Identifier for this simulation setup."
- **Input files** (dropdowns listing matching files in the experiment directory, with `dir/` prefixes and sizes):
  - GROMACS: **Run input (.tpr)** — "GROMACS run input file (.tpr) used to start the simulation."
  - AMBER: **Topology** (`.prmtop`/`.parm7`), **Run control** (`.mdin`/`.in` — "AMBER run control file (.mdin). Outputs are written next to it."), **Coordinates** (`.inpcrd`/`.rst7`).
  - Both engines: **Reference structure** (`.gro`/`.pdb`) — "Structure matching the trajectory atom set and order. Created by the setup notebook." **Required for both engines.**
- **Output paths**: **Trajectory** (`.xtc` for GROMACS, `.nc` for AMBER — "Trajectory file. Auto-filled from run input name." on GROMACS, "…from run control name." on AMBER); GROMACS additionally **Final run structure** (`.gro`).
- **Runtime options**: an extra-flags input (placeholder "No CLI Flags") — "Additional GROMACS/AMBER CLI flags passed to mdrun." Appended verbatim to the engine command line at run time.

Auto-fill: picking the run input (GROMACS) or control file (AMBER) pre-fills the name from the file stem and the trajectory (and, for GROMACS, the final run structure) next to that file. The reference structure is **not** auto-filled and must be picked explicitly.

Click **"Create simulation"** (or **"Save changes"** when editing; the button stays disabled until the form is valid). The manifest is written to the experiment directory as `<name>.simulation.json`, and a `Simulation "<name>" created/saved` toast confirms. Empty file listings show "No files available yet"; a **"None"** entry clears a selection. Client-side validation messages: "Required", "Letters, digits, dots, dashes, and underscores only" (name), "Not a valid experiment-relative path" (outputs).

## The simulation manifest

The manifest is the contract every later step uses. It declares per-role file paths and extra args. Paths are written **relative to the manifest file's own directory** — a manifest created by a notebook at `gromacs/dnarna/hammerhead.simulation.json` references `production/hammerhead.tpr` for `gromacs/dnarna/production/hammerhead.tpr`. (Experiment-relative paths in older manifests keep working as a fallback.) Roles:

| Role | Label | Purpose |
|---|---|---|
| `run_input` | Run input | GROMACS `.tpr` used to start the simulation (required for GMX launch) |
| `topology` | Topology | AMBER `.prmtop` (required for AMBER launch) |
| `coordinates` | Coordinates | AMBER `.inpcrd`/`.rst7` (required for AMBER launch) |
| `control` | Run control | AMBER `.mdin` (required for AMBER launch) |
| `reference_structure` | Reference structure | structure matching the trajectory atom set (required; used by Analyze and the 3D viewer) |
| `trajectory` | Trajectory | expected trajectory output path |
| `run_structure` | Final run structure | GROMACS final structure output path |

Validation rules that make a simulation **invalid** ("Invalid" badge on the form header): missing required roles; an engine mismatch with the experiment ("The simulation engine 'X' does not match the experiment's 'Y' engine."); file names or paths containing characters outside `A–Za–z0–9_.-` and `/` (no spaces, no `..`, no absolute paths). Files that don't exist on disk don't invalidate the manifest — they render a **"missing"** badge next to the field and are rejected when a job is started ("Missing files for: 'Reference structure', 'Trajectory'"). Validation errors are shown in plain English in a **"Manifest validation failed"** alert, e.g. "Missing required file role: 'Topology'."

## Locked simulations and deletion

Once any tuner or production job references a simulation (or its manifest was made read-only), it becomes **locked**: the form shows a **"Locked"** badge with all fields disabled (per-role present/missing badges remain visible) and no submit button. The only action is **Delete** in the tab's ⋯ menu, which asks `Delete simulation "<name>"?` and also deletes its tuner, simulation, and analysis jobs.

To change parameters of a locked simulation: delete it (and its jobs) and create a new one via **"New simulation"** (the old manifest stays intact until deleted). There is no duplicate/copy action yet.
