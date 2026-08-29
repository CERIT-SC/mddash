# Wizard Step 2: Tune

The Tune step benchmarks execution configurations of the simulation and reports measured performance, estimated runtime, and estimated cost — so the production run uses the fastest or cheapest configuration instead of guesswork. It is also the only place a production run can be started: the Run step is a monitoring view that receives the submitted run.

## Layout

The step is titled **"Tune your simulation"** (*"Tuning runs your simulation briefly across different hardware settings to find the fastest one."*) and offers two configuration-method tabs (kept in the URL as `?mode=manual`):

- **"Tuning"** — the guided benchmark flow (default).
- **"Manual configuration"** — submit a run directly with hand-picked parameters, no benchmarks.

The footer always offers **"Back"** (to Setup) and **"Run Simulation"** (start the production run; enabled once a configuration is picked or filled in).

## Starting a tuning job

On the **"Tuning"** tab:

- The **"Number of steps"** field sets the length of each tuning trial (tooltip: "Length of each tuning trial in MD steps. Longer trials give more reliable estimates but take longer."). It is a select with presets **10,000** ("quick, less precise"), **25,000** ("recommended"), **50,000** ("for large systems"), and **"Enter custom value…"**, which swaps to a number input (with a "Back to presets" undo button).
- **"Start tuning"** opens a confirmation dialog — **"Start tuning with 25,000 steps?"** — *"Tuning at this size usually takes several minutes. You can close the page — it keeps running, and you can stop it from this step."* Confirm to start ("Tuning started" toast).
- The button is disabled while the simulation isn't ready: a warning alert titled **"Finish setup first"** explains — "The simulation manifest is invalid." and/or "Missing files: Run Input." (role labels; AMBER: Topology / Coordinates / Run control) — followed by "Go back to the Setup step to fix this before tuning."

The Tuner generates a grid of trials automatically:

- **GROMACS trials**: combinations of MPI processes (`np`: 1, 2, 4, 8), OpenMP threads per rank (`ntomp`: 1, 2, 4, 8), and device assignments for non-bonded (`nb`) and PME calculations on CPU vs GPU. Invalid combos are excluded (e.g. PME on GPU with more than one MPI rank; non-bonded on CPU with PME on GPU).
- **AMBER trials**: GPU configs first — `pmemd.cuda` (single rank) with both Ewald presets — then CPU configs, `pmemd.MPI` with 2–8 ranks and 1–8 threads (up to 32 CPUs), both presets. The Optimized Ewald preset gives roughly 15–20% speedup on GPU.
- The tuner prunes unpromising trials early (after a short warmup, trials that are both much slower and much more expensive per step than the best-so-far are skipped), so fewer rows may appear than the full grid.

While the tuner job runs, its status is polled every 5 seconds. Statuses: PENDING (starting), RUNNING, FINISHED, ERROR, UNKNOWN. If the job reads UNKNOWN with no trials arriving for a while, a warning appears: **"The tuner is not responding"** — tuning keeps retrying on its own; you can also stop the job and try again later.

## The trials table

Each trial (one short benchmark run) is a row. Columns, each with a question-mark hint tooltip:

- **Pick** (radio) — choose the configuration for the production run. Radios are enabled only for FINISHED trials with measured performance.
- **Status** — in-flight trials show a spinner; failed trials show a **"Failed"** badge plus an icon button (aria-label "View output of failed trial …") opening the **"Trial output"** dialog with **"Standard output"** / **"Standard error"** tabs ("Logs reported by the tuner for this trial."). Stopping a tuning job keeps only trials with measurements, so failed rows (and their logs) disappear.
- **Performance** — measured throughput in ns/day ("Throughput measured during the tuning run (ns of simulated time per day). Higher is faster."); em-dash when not yet measured.
- **Est. time** — estimated wall-clock time for the full production simulation with this configuration.
- **Est. cost** — estimated compute cost for the full production simulation with this configuration (derived from hourly CPU/GPU/RAM rates).
- Engine hardware, after a divider — GROMACS: **PME** and **NB** (shown as CPU/GPU); AMBER: **Binary** and **Ewald**.
- **MPI processes** and **Threads** (the trial's np and ntomp).

Rows are grouped: a **"Suggested"** band on top holds the fastest and the cheapest trials (one row can hold both), followed by **"Other configurations"** sorted best-performance-first; unmeasured trials follow in arrival order. While the job is live with no rows yet, a spinner reads "Waiting for the first trials…".

## Recommendation badges

Finished trials with measurements can earn:

- **Fastest** (lightning icon) — highest measured performance of all finished trials.
- **Eco** (green leaf icon) — lowest estimated full production cost.

## Picking a configuration and starting the run

1. Select a trial's radio button. A **"Customize selected configuration"** collapsible appears under the table, pre-filled with the trial's settings (GROMACS: PME, NB, MPI processes, threads; AMBER: Binary, Ewald preset, MPI processes, threads). Values remain editable.
2. On the **"Manual configuration"** tab the same hardware form is offered directly (no trial needed): GROMACS — "PME (Particle Mesh Ewald)" and "NB (Non-bonded interactions)" (CPU/GPU selects); AMBER — "Binary" (`pmemd.cuda (GPU)` / `pmemd.MPI (CPU)`) and "Ewald preset" (Default / Optimized); both — "MPI Processes (MPI ranks)" and "Threads" number inputs.
3. Click **"Run Simulation"** — the production job starts ("Run started" toast) and the wizard advances to the **Run** step. On failure you stay on Tune with an error toast.

The picked trial is remembered in the URL (`?trial=`) and survives tab switches.

## Stopping and restarting a tuning job

- While running: a red-outline **"Stop tuning"** button stops immediately (no confirmation); the toast reads **"Tuning stopped — results so far are kept"**. Finished trials remain usable.
- After stopping (or finishing): a **"Re-tune"** button opens **"Discard tuning results?"** — *"Re-tuning deletes the current results for this simulation and starts over. This cannot be undone."* — with **"Keep results"** / **"Re-tune"**.
- A failed job shows a **"Tuning failed"** alert with the tuner's error message and a **"Tune again"** button (pre-filled with the same number of steps).

## Gotchas

- One tuner job per simulation at a time.
- The trial count shown while running is fixed (the "Number of steps" field renders disabled); changing it requires re-tuning.
- Tuning runs as short benchmark jobs on the cluster; the full production cost/time figures are extrapolations from those measurements.
- Badges and suggested bands only consider FINISHED trials with measured data.
- Only failed trials expose logs (and stopping the job drops those rows).
- A Tuner service restart marks in-flight tuning jobs failed — if an active tuning job suddenly fails for no apparent reason, just start a new tuning job.
