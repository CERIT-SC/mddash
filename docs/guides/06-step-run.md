# Wizard Step 3: Run

The Run step launches nothing itself — the production run is submitted from the **Tune step** ("Run Simulation"). This step monitors the running simulation: live progress, logs, and lifecycle actions. It acts on the currently selected simulation tab.

## No run in progress

With no job for this simulation, the step shows **"No run in progress — taking you back to tuning…"** and automatically returns to the Tune step. The same happens if the job is deleted from elsewhere.

## Live status view

While a job exists, the step is titled **"Run your simulation"** (*"This step runs your full simulation with the configuration below. It can take a while — you'll be able to leave the page and come back to check progress."*) and shows:

- **Progress** — a headline reading **"Preparing"** (with spinner) while step counts cannot yet be parsed from the engine log, then a large percentage (e.g. "20%") with a progress bar (aria-label "Simulation progress"), the step counter ("2,000 / 10,000 steps"), and, when the server can estimate it, **"About 2m 22s remaining"**. A finished run reads **"Finished"** (bar turns green) with the final step count; a failed run reads **"Failed"** with the hint "The run failed — check the logs below for details." A stopped run reads **"Stopped"** with the note *"The run was stopped. Results so far are kept, ready to extend from its checkpoint."*
- While the run is live, the wizard's **Run** marker in the stepper shows a green **progress ring** with the percentage (e.g. "Run · 20%").
- **"Configuration used"** — a single-row table describing the submitted configuration: Performance, Est. time, Est. cost, PME/NB (GROMACS) or Binary/Ewald (AMBER), MPI processes, and Threads. When the configuration matches a tuner trial, the row carries that trial's estimates and **Fastest**/**Eco** badges; otherwise estimate cells show "—".
- Lifecycle actions:
  - While live: **"Stop run"** (red outline) — dialog **"Stop this run?"**: *"The simulation stops at its next checkpoint. Everything produced so far (results, trajectory, and logs) is kept, so you can analyze it or extend the run later."* with **"Keep running"** / **"Stop run"**. Stopping is **not destructive** — nothing is deleted and the run page stays open.
  - When finished, stopped, or failed (GROMACS only): **"Extend"** — dialog **"Extend the run?"** with an **"Additional steps"** input (shows the resulting cumulative total, e.g. "Extends the run from 10,000 to 60,000 total steps"). Extending resumes the simulation from its latest checkpoint and appends to the existing trajectory and logs with the same configuration. AMBER has no Extend yet.
  - When finished, stopped, or failed: **"Re-run"** — dialog **"Re-run the simulation?"**: *"The whole run history (all segments, results, and logs) will be deleted, and the run starts over with the same configuration. This cannot be undone."* with **"Cancel"** / **"Re-run"**. Re-running is the destructive reset; to change parameters, go back to Tune.
- **"Run history"** — a table listing the run's segments (the initial run plus every extension) with their status, step counts, performance, and start time.
- Footer navigation: **"Back"** (to Tune) and **"Analyze"** (enabled while running or once the run finishes or is stopped).

There is no separate pause action — use **Stop run**: it keeps all data, and (GROMACS) the run can later be continued with **Extend**. **Only starting a run (from Tune) or re-running deletes previous result files of that simulation** (GROMACS: `.edr`/`.gro`/`.log`/`.trr`/`.xtc`/`.cpt`; AMBER: `.nc`/`.rst7`/`.mdinfo`/`.out` next to the control file) and marks the manifest read-only. Extra arguments from the manifest are appended to the engine command verbatim.

Status refreshes every 5 seconds while the job is live and stops at FINISHED/STOPPED/ERROR. Jobs keep running on the cluster even if the browser is closed; finished jobs are auto-cleaned from the cluster after 1 hour but their record and logs remain in MDDash.

## What is executed

- **GROMACS**: `mpirun -np <np> gmx mdrun -ntomp <n> -nb <nb> -pme <pme> -deffnm <tpr-stem> <extra_args>` run next to the run-input file, with `np × ntomp` CPUs, 4 GiB RAM per rank, and one GPU when `-nb` or `-pme` is GPU. There is **no grompp step** — the user must supply a ready `.tpr` (typically produced by the setup notebook).
- **AMBER**: `pmemd.cuda` (single GPU) or `mpirun -np <np> pmemd.MPI` (`np × ntomp` CPUs), `OMP_NUM_THREADS=ntomp`. The **Ewald preset** (Default/Optimized, chosen on the Tune step) patches the `&ewald` namelist of the control file in place before running (Optimized ≈ 15–20% GPU speedup). Outputs are written next to the control file, named from its stem (`.out`, `.rst7`, `.nc`, `.mdinfo`).

## Logs

A collapsible **"Logs"** section (collapsed by default, with a total line-count badge) appears once the job leaves PENDING — nothing is fetched while the pod is starting. It contains tabs **"Gromacs log"** (AMBER: **"Amber log"**), **"Standard output"**, and **"Standard error"**, each with its own line-count badge ("empty" when the stream has no lines).

The log viewer behaves like a terminal (ANSI colors, overwriting lines). A **"Follow output"** checkbox (checked by default) auto-scrolls to the bottom on new data; **"Copy \<stream\>"** and **"Download \<stream\>"** buttons act on the active tab. Only the visible stream is fetched, refreshed every 5 seconds while the run is live. The viewer shows the **last 10,000 lines** — when that window caps, a note reads "Showing the last 10,000 of 12,000 lines". Loading reads "waiting for output..."; an empty stream reads e.g. "Standard error is empty."; a failed fetch reads "The log could not be loaded."

When a run fails, the Logs section opens automatically on the **Standard error** tab.

Progress and performance figures are parsed from these logs server-side; if parsing fails, the percentage simply stays at "Preparing".

## Gotchas

- **"Preparing" can last a while** when the cluster is busy or a GPU is being allocated — there is no queue-position indicator.
- Re-running deletes and overwrites outputs for that simulation (the re-run dialog warns about it), and the manifest stays intact.
- **Extending a just-stopped run may take a moment to become available**: the final checkpoint must reach object storage and sync back before Extend accepts it — if Extend reports a missing checkpoint, try again shortly.
- A stopped GROMACS run retains its checkpoint (written on the stop signal) so Extend can resume with no lost progress. Stopping AMBER keeps the trajectory up to the last sync; a resumption point exists only if the control file writes restarts periodically (`ntwr`).
- For AMBER, the Ewald preset **modifies the control file in place** — check the `.mdin` afterwards if hand-editing it.
- Trajectory/final-structure paths in the manifest are expectations of where engine output lands; GROMACS actually writes next to the `.tpr` stem and AMBER next to its control file stem. Custom layouts must keep these consistent, otherwise Analyze will report missing files.
- The simulation manifest's `extra_args` must not contain `-cpi` if you want to use Extend — checkpoint input is managed by the extend flow (any `-nsteps` override is folded into the new cumulative total).
- Only one *live* production job per simulation (a live segment blocks extend) — for parallel replicas create additional simulations via the **"New simulation"** button on the tab bar.
