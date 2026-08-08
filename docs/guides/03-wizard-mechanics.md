# The Experiment Wizard: Steps, Stepper, and Simulations

The wizard (`/<id>/wizard`) is the main working view of an experiment. This guide explains the mechanics common to all five steps; per-step details are in separate guides.

## Page structure

1. **Experiment name** — displayed in a centered card; click the pencil icon to edit inline, then confirm with the check button (or Enter) / cancel with ✕ (or Escape). Renaming an experiment is only possible here, not on the Home page.
2. **Stepper** — five step icons in a row with connector lines: **Setup → Tune → Run → Analyze → Publish** (icons: atom, sliders, play, bar chart, upload).
3. **Simulation tabs** — one tab per simulation defined in the experiment, plus a **"+ New setup"** tab.
4. **Step content** — the active step's panel (Setup form, tuner table, run panel, analysis panel, publish panel).

## How steps unlock

The wizard does not have a "Next" button. Progress is computed on the server from what exists in the experiment, and the frontend polls it every 5 seconds:

| Step | Unlocks when |
|---|---|
| Setup → Tune | at least one valid simulation manifest (`.simulation.json`) exists for the experiment |
| Tune → Run | a tuning trial finished with measured performance — **or** the user clicked "Skip Tuning" |
| Run → Analyze | a simulation job exists (Analyze is reachable even while the job is still RUNNING) |
| Analyze → Publish | a simulation job has FINISHED |
| Publish complete | an MDRepo draft/published record exists |

Stepper visuals: the active step is a large colored circle; completed steps are green; future (locked) steps are grey. Clicking a step icon jumps to it — but only up to the highest unlocked step; clicking further ahead does nothing. Going *backwards* is always allowed.

## Simulation tabs and multi-simulation experiments

An experiment can contain several simulations (e.g. replicated runs or different setups of the same system). The tab bar under the stepper lists them:

- Each tab shows the simulation **name**.
- A **lock icon** means the simulation is *locked* — it is referenced by a tuner or production job (or its manifest was made read-only) and can no longer be edited, only deleted.
- A **red alert icon** means the simulation is *invalid* — its manifest fails validation (missing role files, bad paths, wrong engine, etc.). Repair it in the Setup step.
- **"+ New setup"** — clears the selection and jumps back to step 0 (Setup) to create another simulation.

The selected tab determines which simulation the Tune, Run, and Analyze steps act on.

## Cross-step behavior to remember

- Wizard state is server-side: refreshing the page or logging back in later returns to exactly the same experiment state and step.
- Jobs started in any step keep running in the background even if the user navigates away or stops the server.
- Tuning can be skipped (a confirmation warns the simulation may run slowly); skipping still unlocks the Run step.
- Deleting a simulation cascade-deletes its tuner and simulation jobs (explicit confirmation required).
