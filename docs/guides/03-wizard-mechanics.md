# The experiment wizard

The wizard (`/dash/experiments/<id>`, route `/experiments/<id>`) is the main working view of an experiment. This guide explains the mechanics common to all steps; per-step details are in separate guides.

## Page structure

1. **Title row.** A fixed "Experiment" heading followed by a chip button showing the experiment's name with a pencil icon (aria-label "Rename experiment"). Clicking it opens a **"Rename experiment"** dialog with a Name field and **Cancel** / **Save** buttons ("Experiment renamed" toast on success). The same row carries the experiment's metadata, separated by dividers: the **source** (e.g. "RCSB PDB (1LYZ)" opens an "Experiment source" dialog with structure metadata and downloads; "Uploaded N files" opens an "Uploaded files" dialog with download links; or a repository link), the **creation date**, and the **notebooks repository** (shortened, links out). Renaming is also available from the Home page card menu. The row ends with the **"Publish…"** button (see "Publish").
2. **Simulation tabs.** One tab per simulation defined in the experiment, plus a **"New simulation"** button to the right (see below).
3. **Step cards.** One card per step in a fixed order, numbered 1 to 4: **Setup**, **Configuration**, **Simulation**, **Analysis**. They stack in a bordered panel under the tabs.

## URL state

The wizard's view state lives in the URL and survives bookmarks and refreshes:

- `?simulation=<name>` for the selected simulation tab (`_new` is the creation view).
- `?source=manual` for the Setup card's "Manual" tab.
- `?trial=<id>` for the tuning trial picked in Configuration.
- `?mode=manual` for Configuration's "Manual configuration" view.
- `?analysis=<name>` and `?tab=analysis` for the analysis picked in the Analysis card and its open tab.
- `?publish=true` while the Publish dialog is open. It survives the MDRepo sign-in round trip.

## How steps unlock

There is no "Next" button. The server computes how far the selected simulation has got, and the frontend polls it every 5 seconds (pausing when nothing is live):

| Card | Opens when |
|---|---|
| Configuration | the simulation has a valid manifest (`.simulation.json`) |
| Simulation | a production run was submitted |
| Analysis | the run has saved its first frames (also mid-run), or it finished or was stopped |

Each card shows its state:

- **Current.** The step being worked on: a highlighted number, content expanded. A running simulation stays current after its first frames open Analysis.
- **Done.** A green check. Setup and Configuration fold to a one-line summary (e.g. `"protein" is ready`) with a **Show** / **Hide** toggle; Simulation and Analysis stay expanded.
- **Locked.** A dashed border, a lock icon, and the reason, e.g. "Available once the setup finishes".

## Publish

Publish is experiment-level, not a step of one simulation. The **"Publish…"** button opens the **"Publish your experiment"** dialog (see "Publish"). Until a run has finished or been stopped (or an MDRepo draft or record exists), the button is disabled and a note under it explains why. It also waits while tuning or a run is live on the selected simulation.

## Simulation tabs and multi-simulation experiments

An experiment can contain several simulations (e.g. replicated runs or different setups of the same system). The tab bar above the step cards lists them:

- Each tab shows the simulation **name**.
- Every tab has an **⋯ "Actions for \<name\>"** menu whose only action is **"Delete"**. Deleting asks `Delete simulation "<name>"?` ("This permanently removes the simulation manifest and all related jobs. This can't be undone.") and removes the manifest plus its tuner, simulation, and analysis jobs. The Setup card's form header shows whether a simulation is *locked* or *invalid* (see "Step 1: Setup"), not the tab.
- **"New simulation".** A link-style button with a plus icon that switches to an unnamed creation tab. While creating, only Setup is open.

Without an explicit `?simulation=`, the wizard selects the experiment's most recently active simulation (its `latest_simulation_path`), falling back to the first in the list. The selected tab determines which simulation the Configuration, Simulation, and Analysis cards act on.

## Cross-step behavior to remember

- Wizard state is server-side, overlaid with URL state. Refreshing the page or logging back in later returns to the same experiment state, and the URL preserves the exact tab view.
- Jobs started in any step keep running in the background even if the user navigates away or stops the server.
- Tuning is optional. Configuration offers a **"Manual configuration"** tab for submitting a run directly with hand-picked parameters (see "Step 2: Configuration").
- Deleting a simulation cascade-deletes its tuner, simulation, and analysis jobs (explicit confirmation required).
- Load failures show a durable error alert (with the problem code and a Retry button), not a toast.
