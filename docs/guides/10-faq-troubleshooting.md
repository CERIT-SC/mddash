# FAQ and Troubleshooting

Frequently asked questions and common issues in MDDash (production deployment).

## Access and navigation

**How do I log in?** Click **"Try MDDash"** on the landing page (or "Sign in with e-INFRA CZ" on the login page) and authenticate with your e-INFRA CZ account.

**Where is the logout button?** In the dashboard header (top right, "Log out"), and on the JupyterHub pages reachable via the header's "Home" link.

**How do I get to JupyterLab?** From an experiment's Setup or Analyze step, start its notebook and click **"Open notebook"** — JupyterLab opens in a new tab deep-linked to the setup/analysis notebook. While the notebook is running, the notebook status bar under the header (present on every experiment page) also carries "Open notebook".

**How do I rename an experiment?** Either from the Home page (the card's ⋯ menu → "Rename") or in the wizard (the pencil chip next to the "Experiment" title).

**I closed my browser — did my simulation die?** No. Tuning, simulation, analysis, and upload jobs run on the cluster independently of the browser. Reopen the experiment to see live status and logs.

## Starting work

**What input data can I start an experiment from?** Uploaded files, an RCSB PDB ID or PDB URL, or a DOI/repository link (works with any InvenioRDM repo such as Zenodo or MDRepo).

**Which engines are supported?** GROMACS and AMBER, chosen at experiment creation (curated workflows fix it; "Use custom workflow" lets you pick) and fixed afterwards.

**What is a workflow / preset?** The git repository of notebooks cloned into the experiment — it provides `setup.ipynb` and `analysis.ipynb`. Curated workflows are the cards on the New Experiment page, grouped by engine and simulation category; you can instead use any custom git repository ("Use custom workflow" — Binder-compatible supported; private HTTPS repos accept an access token used only for cloning).

**The wizard step I want is greyed out.** Steps unlock automatically: Tune needs a valid simulation manifest, Run needs tuning results (or a manually configured run), Analyze is reachable while the run is going, Publish needs a finished simulation job or an existing MDRepo draft.

## Simulations and manifests

**What is a `.simulation.json`?** The simulation manifest — the file that defines which experiment files play which roles (run input, topology, coordinates, control, reference structure, trajectory) plus extra engine flags. Every job is based on it. Created by the setup notebook or manually in the Setup step's simulation form ("From Notebook" / "Manual" tabs).

**My simulation shows an "Invalid" badge.** The manifest is invalid: missing required roles, wrong engine, or paths with unsupported characters (no spaces, no `..`, relative paths only). Open the Setup step, select the simulation, and repair the fields — the "Manifest validation failed" alert lists exactly what's wrong, e.g. "Missing required file role: 'Topology'." Files that are missing on disk show a "missing" badge and are rejected when a job starts.

**Tuning can't start — "Finish setup first".** The alert lists the blockers: "The simulation manifest is invalid." and/or "Missing files: Run input (.tpr)." (AMBER needs Topology + Coordinates + Run control). Fix the manifest/files in the Setup step.

**Why can't I edit my simulation?** It's locked — a tuner or production job references it. Delete it (with its jobs) and create a new simulation to change it.

## Running jobs

**My run says "Preparing" and nothing happens.** The pod is being scheduled or waiting for resources (possibly a GPU). There is no queue indicator — it will start when resources free up.

**How do I cancel/stop a simulation job?** On the Run step, **"Stop run"** (confirm in the "Stop this run?" dialog — stopping deletes the run, its progress so far, and its logs). There is no pause; **"Re-run"** restarts with the same configuration, and changing parameters means going back to the Tune step.

**Re-running deleted my previous outputs.** By design — starting or re-running a run removes previous result files of that simulation (trajectory, structures, logs). Keep copies if you need them.

**Where are my logs?** Run step → the collapsible **"Logs"** section (tabs: Gromacs log / Amber log / Standard output / Standard error). The viewer shows the last 10,000 lines and can follow or copy/download each stream. Logs appear only once the job leaves PENDING.

**AMBER: my .mdin file changed.** Expected — the Ewald preset option rewrites the `&ewald` namelist in the control file in place before each run.

**GROMACS: there's no grompp step.** Correct — MDDash runs `gmx mdrun` from a ready `.tpr`. Build it with the setup notebook or upload one.

## Tuning, analyzing, publishing

**Do I have to tune?** No — on the Tune step's **"Manual configuration"** tab you can submit a run directly with hand-picked parameters. Tuning tells you the fastest (ns/day) and cheapest (est. cost) execution configuration, so it is recommended.

**What do the Fastest / Eco badges mean?** Highlights over finished trials: highest measured ns/day, and lowest estimated full-run cost. The "Suggested" band at the top of the trials table holds both.

**Why did an analysis "produce no data"?** The analysis doesn't apply to the system — typically a membrane analysis on a system with no lipid bilayer. It's not an error.

**Why is Calculate disabled?** No usable simulation selected, the trajectory file doesn't exist yet, or another analysis job is still running (one at a time per simulation).

**Why don't I see the imaging preprocessing options?** "Image Only" / "Image and Fit" require a GROMACS `.tpr`; AMBER only supports "Use Files As-Is".

**Publishing asks me to connect to MDRepo again.** The MDRepo OAuth token lives in the browser session; a new session needs a new one-time authorization.

**My upload to MDRepo failed.** The draft and already-uploaded files are preserved — inspect the failed-files list and click **"Retry upload"**.

**Where is my DOI?** MDDash only creates an MDRepo **draft** and uploads files. Open the draft (button "View in MDRepo"), fill/review metadata in MDRepo, and publish there to mint the DOI.

## Storage and quota

**How big is my storage?** Each user has a persistent volume whose size is deployment-configured. See live usage and the limit in the server status bar under the dashboard header ("Storage: X / Y").

**Are my files on S3?** Mostly — sync is automatic (~10 s cadence), but large raw outputs (`*.edr`, `*.xtc`, `*.tpr`, `*.cpt`, `*.gro`, `*.log`, caches) are excluded and live only on the volume. Deletions propagate in both directions.

**A "Notebook limit reached" dialog appeared.** You hit the concurrent-notebook cap — stop one of your running notebooks (from the dialog or a card menu) to free a slot.

**"Resource quota exceeded. Please stop other notebooks."** Your namespace allocation lacks headroom — check the storage readout in the server status bar, then stop notebooks or delete old experiments.

**A new file isn't showing in a file picker.** The UI refreshes on a cadence of a few seconds — retry shortly.

## Glossary

| Term | Meaning |
|---|---|
| Experiment | one project in MDDash; owns simulations, jobs, notebooks, files |
| Simulation (manifest) | `.simulation.json` assigning roles to files for one runnable simulation |
| Tuner / trial | benchmarking service; a trial is one benchmark short run of a specific config |
| Job | any cluster task: tuning, simulation, analysis, MDRepo upload |
| Notebook | per-experiment JupyterLab environment |
| MDRepo | InvenioRDM repository used for publication (draft records → DOI) |
| Statuses | PENDING (starting), RUNNING, FINISHED, ERROR, UNKNOWN (couldn't fetch) |
