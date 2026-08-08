# Wizard Step 3: Run

The Run step launches and monitors the production MD simulation. It acts on the currently selected simulation tab. With no job yet, it shows a start form; once a job exists, it shows live status, progress, and logs.

## Start form — GROMACS ("Start simulation")

| Field | Description |
|---|---|
| **Number of MPI processes (np)** | MPI ranks, maps to `mpirun -np` |
| **OpenMP threads per MPI rank (-ntomp)** | threads per rank (`-ntomp`, `OMP_NUM_THREADS`) |
| **Device type for non-bonded interactions (-nb)** | CPU / GPU / Auto |
| **Device type for PME calculations (-pme)** | CPU / GPU / Auto |

When arriving from the Tune step with a selected trial, these are pre-filled with the trial's configuration. A GPU is requested automatically when `-nb` or `-pme` is set to GPU.

There is **no grompp step** — the user must supply a ready `.tpr` (typically produced by the setup notebook). The executed command is effectively `mpirun -np <np> gmx mdrun -ntomp <n> -nb <nb> -pme <pme> -deffnm <tpr-stem> <extra_args>` run next to the run-input file, with resources of `np × ntomp` CPUs, 4 Gi RAM per rank, and one GPU if requested.

## Start form — AMBER ("Start AMBER simulation")

| Field | Description |
|---|---|
| **Binary** | `pmemd.cuda (GPU)` or `pmemd.MPI (CPU)` |
| **Ewald Preset** | Default or Optimized — patches the `&ewald` namelist of the control file in place before running (Optimized ≈ 15–20% GPU speedup) |
| **Number of MPI processes (np)** | used for `pmemd.MPI` (`mpirun -np`) |
| **OpenMP threads per MPI rank (ntomp)** | `OMP_NUM_THREADS` |

AMBER outputs are written next to the control file, named from the control file's stem (`.out`, `.rst7`, `.nc`, `.mdinfo`).

## The Run button

Disabled (with the reason printed below it, e.g. "Select a simulation first.", "Selected simulation is invalid.", "Missing required files: run_input.") until the selected simulation is valid and has its launch files: GROMACS requires `run_input` (.tpr); AMBER requires topology, coordinates, and control.

**Starting a run deletes previous result files of that simulation** (GROMACS: `.edr`/.`gro`/`.log`/`.trr`/`.xtc`/`.cpt`; AMBER: `.nc`/`.rst7`/`.mdinfo`/`.out` next to the control file) and marks the manifest read-only. Extra arguments from the manifest are appended to the command verbatim.

## Live status view

While a job exists, the panel shows:

- **Status** chip: PENDING (yellow, pulsing — job created, pod starting/scheduling; no logs yet), RUNNING (yellow), FINISHED (green), ERROR (red), UNKNOWN (grey — status could not be fetched; last known state kept).
- **Delete job** (red outline) — *"Delete this simulation job? This cannot be undone."* This is the only lifecycle action: deletion stops a running job and removes its record. **There is no cancel/pause/restart button — to stop a run, delete the job; to re-run with other parameters, delete and submit again.**
- While RUNNING (when step counts can be parsed from the engine log): **Progress** — percent bar, "X / Y steps", and "Estimated time remaining: …".
- When FINISHED: **Job Summary** with **Performance** (ns/day) and **Total Runtime**.
- **Simulation Parameters** — the submitted configuration (GROMACS: "Processes: np × ntomp threads", "PME / NB"; AMBER: Binary, Ewald, Processes).

Status refreshes every 5 seconds while the job is active and stops polling at FINISHED/ERROR. Jobs keep running on the cluster even if the browser is closed; finished jobs are auto-cleaned from the cluster after 1 hour but their record and logs remain in MDDash.

## Logs

Available once the job leaves PENDING, via a dropdown:

- GROMACS: **Gromacs Log** (the engine `.log`), **Standard Output**, **Standard Error**.
- AMBER: **mdout**, **mdinfo**, **Standard Output**, **Standard Error**.

The log viewer behaves like a terminal (colors, overwriting lines), auto-scrolls to the bottom on new data, and refreshes every 5 seconds while the job runs. It shows the **last 100 lines** ("…" marks truncation); "waiting for output..." appears while loading and "(no output)" when empty. Progress/performance figures are parsed from these logs server-side; if parsing fails, those panels simply don't appear.

## Gotchas

- **PENDING can last a while** when the cluster is busy or a GPU is being allocated — there is no queue-position indicator.
- Re-running overwrites outputs for that simulation, and the start form doesn't warn about it separately (the simulation manifest stays intact).
- For AMBER, the Ewald preset **modifies the control file in place** — check the `.mdin` afterwards if hand-editing it.
- Trajectory/final-structure paths in the manifest are expectations of where engine output lands; GROMACS actually writes next to the `.tpr` stem and AMBER next to its control file stem. Custom layouts must keep these consistent, otherwise Analyze will report missing files.
- Only one production job per simulation — for parallel replicas create additional simulations via the "+ New setup" tab.
