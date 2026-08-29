# MDDash Overview

MDDash is a browser-based Virtual Research Environment for molecular dynamics (MD) simulations. It lets users prepare, tune, run, analyze, and publish MD simulations without leaving the browser. It supports the GROMACS and AMBER engines.

Authentication is via e-INFRA CZ single sign-on ("Sign in with e-INFRA CZ"); any e-INFRA CZ account can sign in.

A Talqo chat assistant widget is embedded on every page (landing, JupyterHub, and dashboard) for in-browser help.

## The five-stage workflow

Every project in MDDash is an **experiment**. Each experiment is driven through a five-step wizard, visible at the top of the experiment page:

1. **Setup** — Get input files into the experiment and define a *simulation manifest* (which files play which roles). Usually done by running a guided setup notebook in JupyterLab.
2. **Tune** — Benchmark the simulation across many execution configurations (CPU/GPU splits, MPI ranks, threads) and see measured performance (ns/day), estimated runtime, and estimated cost for the full production run. Optional; can be skipped.
3. **Run** — Launch the production MD simulation as a cluster job with chosen parameters.
4. **Analyze** — View the trajectory in a 3D Mol* viewer and run built-in analyses (RMSD, PCA, hydrogen bonds, membrane metrics, energies, and more) as cluster jobs.
5. **Publish** — Upload the experiment to MDRepo (InvenioRDM) as a draft record that can be published with a DOI, or export to MDPosit.

Steps unlock automatically as the underlying work completes — users can always click back to earlier steps.

## Key concepts

- **Experiment** — the top-level project unit. Created on the **New Experiment** page (`/new`) by picking a curated workflow card (or a custom notebooks repository) and providing a name, an MD engine (GROMACS or AMBER; fixed for the lifetime of the experiment), and initial data (a PDB structure, file upload, or a DOI/repository link).
- **Simulation manifest (`.simulation.json`)** — a small JSON file inside the experiment directory that assigns *roles* to files (run input, topology, coordinates, control file, reference structure, trajectory) and holds extra engine flags. It is the single source of truth every job is based on. Created by the setup notebook or manually via the simulation form in the Setup step.
- **Jobs** — tunings, simulations, analyses, and uploads all run as Kubernetes jobs on the cluster. They keep running even if the user closes the browser; status and logs are available on return. Statuses: PENDING, RUNNING, FINISHED, ERROR, UNKNOWN.
- **Notebook** — a per-experiment JupyterLab environment (MD workstation with GROMACS, AmberTools, NGL). Started on demand from the Home page, the Setup step, or the Analyze step.
- **Personal storage** — all experiment files live on a persistent personal volume and are continuously mirrored to S3.

## Where things are

- **Landing page** (`/`): public overview of MDDash with **"Try MDDash"** / **"Launch MDDash"** buttons.
- **JupyterHub home** (`/hub/home`): start/stop the personal server (the pod the whole UI runs in); server status, API tokens (`/hub/token`), and log out.
- **Dashboard Home** (`/dash`): "My Experiments" — experiment cards grouped by notebook state, with search, sorting, and the **"New"** button. A server status bar under the header shows uptime and storage usage.
- **New Experiment** (`/dash/new`): workflow selection — curated workflow cards grouped by engine (filterable via tabs), each opening the creation dialog; own git repositories via "Use custom workflow".
- **Experiment Wizard** (`/dash/experiments/<id>`): the five-step workflow. The active step, simulation, and related state are reflected in the URL (`?step=`, `?simulation=`), so a link returns to the exact same view.
- Unknown dashboard URLs show a "Page not found" screen.
