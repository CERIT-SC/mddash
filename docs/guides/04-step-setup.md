# Wizard Step 1: Setup

The Setup step (step 0) is where input data becomes a runnable simulation definition. Goal: end up with at least one valid **simulation manifest** (`.simulation.json`) — either produced by the setup notebook or created manually in the editor.

## Page layout

- **Experiment Details** card: Creation Date, Creation Method (how the experiment was initialized), Notebook Repository (the git repo cloned at creation).
- **Notebook controller** (right side): start/stop/open the experiment's JupyterLab environment.
- **Create/Edit Simulation** card below.
- A footer hint appears while no valid simulation exists: *"Run the setup notebook to generate a simulation manifest, or create one above. At least one valid simulation is required to continue."*

## Using the setup notebook (guided path)

1. In the notebook controller, pick a **Size** from the offered tiers (each tier is shown with its CPU/RAM, e.g. `1x · N cores / M GB`) and optionally tick the **GPU** checkbox, then click **Start**.
2. Wait through the states: PENDING ("Your notebook is starting up. This may take a minute.") → INITIALIZING ("Your notebook is setting up the environment. This may take a few minutes if using Binder repository.") → RUNNING.
3. Click **Open** — JupyterLab opens in a new tab with the **setup.ipynb** notebook already loaded (a deep link into the experiment directory).
4. Run the notebook cells. It fetches/builds the system (from the PDB, repository, or uploaded data), prepares engine input files, and writes a `*.simulation.json` manifest into the experiment directory.
5. Back in the dashboard, the wizard auto-detects the manifest within ~5 seconds and unlocks the Tune step.

Notebook controller behaviors: a **Stop** button (red) is available while running/starting; on ERROR the button becomes a yellow **Respawn**; while running it shows badges for the active tier's CPU/RAM and GPU. The number of notebooks that can run at once per user is limited — exceeding it fails with the toast "Maximum of N concurrent notebook(s) reached. Stop one first." If the namespace quota has no headroom, a "Resource quota exceeded" toast appears instead.

## Creating a simulation manually (editor path)

The **Create Simulation** card is useful when runnable engine files already exist (e.g. uploaded `.tpr`, or an AMBER `.prmtop`/`.inpcrd`/`.mdin` trio). Fields:

- **Name** — "Identifier for this simulation setup."
- **Existing files** (dropdowns listing matching files in the experiment directory):
  - GROMACS: **Run input** (`.tpr`) — "GROMACS run input file (.tpr) used to start the simulation."
  - AMBER: **Topology** (`.prmtop`), **Coordinates** (`.inpcrd`/`.rst7`), **Run control** (`.mdin`).
  - Both: **Reference structure** (`.gro`/`.pdb`) — "Structure matching the trajectory atom set and order. Created by the setup notebook."
- **Output paths**: **Trajectory** (`.xtc` for GROMACS, `.nc` for AMBER — "Trajectory file. Auto-filled from run input name."); GROMACS additionally **Final run structure** (`.gro`).
- **Runtime options**: **Extra arguments** — "Additional GROMACS/AMBER CLI flags passed to mdrun." Appended verbatim to the engine command line at run time.

Auto-fill: picking the run input (GROMACS) or control file (AMBER) pre-fills still-empty fields — the name from the file stem, trajectory and run structure paths next to that file, and the reference structure at `analysis/<stem>-reference.gro`.

Click **Create** (or **Save** when editing). The manifest is written to the experiment directory as `<name>.simulation.json`.

## The simulation manifest

The manifest is the contract every later step uses. It declares per-role file paths and extra args. Roles:

| Role | Label | Purpose |
|---|---|---|
| `run_input` | Run input | GROMACS `.tpr` used to start the simulation (required for GMX launch) |
| `topology` | Topology | AMBER `.prmtop` (required for AMBER launch) |
| `coordinates` | Coordinates | AMBER `.inpcrd`/`.rst7` (required for AMBER launch) |
| `control` | Run control | AMBER `.mdin` (required for AMBER launch) |
| `reference_structure` | Reference structure | structure matching the trajectory atom set (used by Analyze and the 3D viewer) |
| `trajectory` | Trajectory | expected trajectory output path |
| `run_structure` | Final run structure | GROMACS final structure output path |

Validation rules that make a simulation **invalid** (red alert icon on its tab): missing required roles; an engine mismatch with the experiment; file names or paths containing characters outside `A–Za–z0–9_.-` and `/` (no spaces, no `..`, no absolute paths); missing files on disk. Validation errors are shown in plain English, e.g. "Missing required file role: 'Topology'." or "This simulation has validation errors. Edit the fields above to repair it."

## Locked simulations and deletion

Once any tuner or production job references a simulation, it becomes **locked**: the Setup step shows a read-only preview (engine badge, per-role files with "present"/"missing" badges, extra args) and only a **Delete** button. Deleting a simulation asks "Delete this simulation and all related jobs? This cannot be undone." and also deletes its tuner and simulation jobs.

To change parameters of a locked simulation: delete it (and its jobs) and create a new one (a "+ New setup" tab keeps the old manifest intact — create a copy instead if old results should be kept).
