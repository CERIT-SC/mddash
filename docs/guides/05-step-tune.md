# Wizard Step 2: Tune

The Tune step benchmarks many execution configurations of the simulation and reports measured performance, estimated runtime, and estimated cost — so the production run uses the fastest or cheapest configuration instead of guesswork. It is optional.

## Starting a tuning job

- Select a simulation in the simulation tab bar. The step shows a **"Configure tuning job"** card with one input — **"Number of steps (nsteps)"** (default **25000**; leaving it empty falls back to the default) — and a **"Start tune job"** button.
- The button is disabled (with an explanation such as "Missing required files: run_input.") while the selected simulation is invalid or lacks launch-required files. GROMACS needs `run_input` (.tpr); AMBER needs topology, coordinates, and control files.
- If **no simulation is selected**, the step shows only a red-outlined **"Skip Tuning"** button with a confirmation dialog: **"Skip Tuning?"** — *"Are you sure you want to skip tuning? Your simulation may run slowly without tuning."* Confirming unlocks the Run step.

Users do not pick configurations by hand — the Tuner generates a grid automatically:

- **GROMACS trials**: combinations of `np` (MPI processes: 1, 2, 4), `ntomp` (OpenMP threads per rank: 1, 2, 4), and device assignments for non-bonded (`nb`) and PME calculations on CPU vs GPU. Invalid combos are excluded (e.g. PME on GPU with more than one MPI rank; non-bonded on CPU with PME on GPU).
- **AMBER trials**: `pmemd.cuda` (GPU) vs `pmemd.MPI` (CPU) binaries, `np`/`ntomp` combinations, and two Ewald presets — Default and Optimized (Optimized gives roughly 15–20% speedup on GPU). GPU configs run first.

While the tuner job runs, its status is polled every 5 seconds. Statuses: PENDING (starting), RUNNING, FINISHED, ERROR, UNKNOWN.

## The trials table

Each trial (one short benchmark run) is a row with columns:

- **Select** — radio button to choose the configuration for the production run.
- **Status** — the trial's job status chip. For ERROR trials a terminal icon button (tooltip "View trial logs") opens the "Trial Logs" dialog with **stdout** and **stderr** tabs (not available once the tuning job was stopped).
- **Performance** — measured performance in ns/day (em-dash when not yet measured).
- **Est. Time** — estimated wall-clock time to run the full simulation with this configuration.
- **Est. Cost** — estimated cost of the full production run at that configuration (derived from hourly CPU/GPU/RAM rates).
- Engine parameters — GROMACS: **PME**, **NB**, **NP**, **NTOMP**; AMBER: **Binary**, **Ewald**, **NP**, **NTOMP**. Hover the question-mark icons for descriptions.

Sorting: finished trials with measurements come first, best performance at the top. Empty states show a spinner with "Waiting for tuning trials..." or, after a stop, "No trials completed. The tuning job was stopped before any trials finished."

## Recommendation badges

Finished trials earn up to one of these badge sets shown on their row:

- **Fastest** (blue, lightning icon) — highest measured performance of all finished trials.
- **Most efficient** (green, leaf icon) — cheapest estimated full production run.
- **Most expensive** (red, dollar icon) — highest estimated cost ("expensive to run").

The top row (highest performance) is treated as the optimal trial.

## Proceeding to the production run

1. Select a trial's radio button.
2. If the selected trial is not the fastest, a confirmation appears: *"The selected trial doesn't have the optimal performance. Are you sure you want to proceed with these parameters?"*
3. A start form appears pre-filled with the trial's configuration (GROMACS: "Start simulation" with np/ntomp/nb/pme; AMBER: "Start AMBER simulation" with Binary/Ewald Preset/np/ntomp). Values remain editable.
4. Click **Run** — the production simulation job starts and the wizard advances to the **Run** step.

## Stopping and deleting a tuning job

- While running: a yellow **Stop** button — *"Are you sure you want to stop the tuning job? Results collected so far will be saved, but any trials still in progress will be lost. This cannot be undone."* Finished trials are kept and usable.
- After stopping: a **Delete job** button — *"Delete this tuning job? This cannot be undone."* — removes it so a fresh tuning run can be started.
- A failed job shows a red "Error:" banner and returns to the configure form to retry.

## Gotchas

- One tuner job per simulation at a time.
- Tuning runs as short benchmark jobs on the cluster; the full production cost/time figures are extrapolations from those measurements.
- Badges only consider FINISHED trials with measured data.
- Only failed trials expose logs (and not after the tuning job was stopped).
- Operator note: active tuner jobs cannot survive a Tuner service restart (they are marked failed) — just start a new tuning job if that happens.
