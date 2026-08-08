# FAQ and Troubleshooting

Frequently asked questions and common issues in MDDash (production deployment).

## Access and navigation

**How do I log in?** Click "Sign in with e-INFRA CZ" on the landing page. First-time users need a lightweight registration approved by the MDDash team.

**Where is the logout button?** Not in the dashboard. Click the house icon in the dashboard header ("Back to JupyterHub") and use **Log out** in the JupyterHub header.

**How do I get to JupyterLab?** From an experiment's Setup or Analyze step, start its notebook and click **Open** — JupyterLab opens in a new tab. There's no direct JupyterLab link outside that flow.

**How do I rename an experiment?** Inside the wizard: click the pencil icon next to the experiment name. It can't be renamed from the Home page.

**I closed my browser — did my simulation die?** No. Tuning, simulation, analysis, and upload jobs run on the cluster independently of the browser. Reopen the experiment to see live status and logs.

## Starting work

**What input data can I start an experiment from?** Uploaded files, an RCSB PDB ID or PDB URL, or a DOI/repository link (works with any InvenioRDM repo such as Zenodo or MDRepo).

**Which engines are supported?** GROMACS and AMBER, chosen at experiment creation and fixed afterwards.

**What is a notebook workflow / curated module?** The git repository of notebooks cloned into the experiment — it provides `setup.ipynb` and `analysis.ipynb`. You can instead use any custom git repository (Binder-compatible supported; private HTTPS repos accept an access token used only for cloning).

**The wizard step I want is greyed out.** Steps unlock automatically: Tune needs a valid simulation manifest, Run needs tuning results (or Skip Tuning), Analyze needs a simulation job, Publish needs a finished simulation job.

## Simulations and manifests

**What is a `.simulation.json`?** The simulation manifest — the file that defines which experiment files play which roles (run input, topology, coordinates, control, reference structure, trajectory) plus extra engine flags. Every job is based on it. Created by the setup notebook or manually in the Setup step's "Create Simulation" card.

**My simulation shows a red alert icon.** The manifest is invalid: missing required roles, files not on disk, wrong engine, or paths with unsupported characters (no spaces, no `..`, relative paths only). Open the Setup step, select the simulation, and repair the fields — validation messages say exactly what's wrong, e.g. "Missing required file role: 'Topology'."

**The Run / Start tune job button is disabled.** The reason is printed below it (e.g. "Missing required files: run_input." for GROMACS; AMBER needs topology + coordinates + control). Fix the manifest/files in the Setup step.

**Why can't I edit my simulation?** It's locked — a tuner or production job references it. Delete it (with its jobs) and create a new setup to change it.

## Running jobs

**My job is stuck on PENDING.** The pod is being scheduled or waiting for resources (possibly a GPU). There is no queue indicator — it will start when resources free up.

**How do I cancel/stop a simulation job?** Delete it ("Delete job" — this stops it). There is no pause/restart; submit again to re-run.

**Re-running deleted my previous outputs.** By design — starting a run removes previous result files of that simulation (trajectory, structures, logs). Keep copies if you need them.

**Where are my logs?** Run step → log dropdown (GROMACS: Gromacs Log / stdout / stderr; AMBER: mdout / mdinfo / stdout / stderr). The viewer shows the last ~100 lines. Logs appear only once the job leaves PENDING.

**AMBER: my .mdin file changed.** Expected — the Ewald Preset option rewrites the `&ewald` namelist in the control file in place before each run.

**GROMACS: there's no grompp step.** Correct — MDDash runs `gmx mdrun` from a ready `.tpr`. Build it with the setup notebook or upload one.

## Tuning, analyzing, publishing

**Do I have to tune?** No — "Skip Tuning" advances straight to Run (with a warning that the simulation may run slowly). Tuning tells you the fastest (ns/day) and cheapest (est. cost) execution configuration.

**What do the Fastest / Most efficient / Most expensive badges mean?** Client-side highlights over finished trials: highest measured ns/day, lowest estimated full-run cost, and highest estimated full-run cost.

**Why did an analysis "produce no data"?** The analysis doesn't apply to the system — typically a membrane analysis on a system with no lipid bilayer. It's not an error.

**Why is Calculate disabled?** No valid simulation selected, the trajectory file doesn't exist yet, or another analysis job is still running (one at a time per simulation).

**Why don't I see the imaging preprocessing options?** "Image Only" / "Image and Fit" require a GROMACS `.tpr`; AMBER only supports "Use Files As-Is".

**Publishing asks me to connect to MDRepo again.** The MDRepo OAuth token lives in the browser session; a new session needs a new one-time authorization.

**My upload to MDRepo failed.** The draft and already-uploaded files are preserved — inspect the failed-files list and click "Retry Upload".

**Where is my DOI?** MDDash only creates an MDRepo **draft** and uploads files. Open the draft (button "View in MDRepo"), fill/review metadata in MDRepo, and publish there to mint the DOI.

## Storage and quota

**How big is my storage?** Each user has a persistent volume whose size is deployment-configured. See live usage and limits in Home → Resource Usage (Storage card).

**Are my files on S3?** Mostly — sync is automatic (~10 s cadence), but large raw outputs (`*.edr`, `*.xtc`, `*.tpr`, `*.cpt`, `*.gro`, `*.log`, caches) are excluded and live only on the volume. Deletions propagate in both directions.

**"Maximum of N concurrent notebook(s) reached."** Stop your other running notebook first.

**"Resource quota exceeded."** Your namespace allocation lacks headroom — check Home → Resource Usage, then stop notebooks/jobs or delete old experiments.

**A new file isn't showing in a file picker.** Storage sync takes a few seconds — retry shortly.

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
