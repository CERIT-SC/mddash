# MDDash Overview

MDDash is a browser-based Virtual Research Environment for molecular dynamics (MD) simulations. It lets users prepare, tune, run, analyze, and publish MD simulations without leaving the browser. It supports the GROMACS and AMBER engines.

Authentication is via e-INFRA CZ single sign-on ("Sign in with e-INFRA CZ"). New users need a lightweight registration approved by the MDDash team before their first login.

## The five-stage workflow

Every project in MDDash is an **experiment**. Each experiment is driven through a five-step wizard, visible at the top of the experiment page:

1. **Setup** — Get input files into the experiment and define a *simulation manifest* (which files play which roles). Usually done by running a guided setup notebook in JupyterLab.
2. **Tune** — Benchmark the simulation across many execution configurations (CPU/GPU splits, MPI ranks, threads) and see measured performance (ns/day), estimated runtime, and estimated cost for the full production run. Optional; can be skipped.
3. **Run** — Launch the production MD simulation as a cluster job with chosen parameters.
4. **Analyze** — View the trajectory in a 3D Mol* viewer and run built-in analyses (RMSD, PCA, hydrogen bonds, membrane metrics, energies, and more) as cluster jobs.
5. **Publish** — Upload the experiment to MDRepo (InvenioRDM) as a draft record that can be published with a DOI, or export to MDPosit.

Steps unlock automatically as the underlying work completes — users can always click back to earlier steps.

## Key concepts

- **Experiment** — the top-level project unit. Created from the Home page with a name, an MD engine (GROMACS or AMBER), initial data (file upload, PDB ID, or a DOI/repository link), and a notebook workflow (a curated analysis notebook or a custom git repository).
- **Simulation manifest (`.simulation.json`)** — a small JSON file inside the experiment directory that assigns *roles* to files (run input, topology, coordinates, control file, reference structure, trajectory) and holds extra engine flags. It is the single source of truth every job is based on. Created by the setup notebook or manually via the "Create/Edit Simulation" form in the Setup step.
- **Jobs** — tunings, simulations, analyses, and uploads all run as Kubernetes jobs on the cluster. They keep running even if the user closes the browser; status and logs are available on return. Statuses: PENDING, RUNNING, FINISHED, ERROR, UNKNOWN.
- **Notebook** — a per-experiment JupyterLab environment (MD workstation with GROMACS, AmberTools, Mol*). Started on demand from the Setup or Analyze step.
- **Personal storage** — all experiment files live on a persistent personal volume and are continuously mirrored to S3.

## Where things are

- **Home page** (`/`): "My Experiments" card grid, "Resource Usage" (CPU/Memory/Storage quota bars), and a Documentation section.
- **New experiment** (`/new`): creation form.
- **Wizard** (`/<id>/wizard`): the five-step experiment workflow.
- **JupyterHub home** (`/hub/home`): start/stop the personal server (the pod the whole UI runs in), API tokens, log out. The dashboard's server bar "Stop server" button routes here with `?stop` (the hub performs the stop) and then shows the hub's stopping page.
