# MDDash overview

MDDash is a browser-based Virtual Research Environment for molecular dynamics (MD) simulations. It lets users prepare, tune, run, analyze, and publish MD simulations without leaving the browser. It supports the GROMACS and AMBER engines.

Authentication is via e-INFRA CZ single sign-on ("Sign in with e-INFRA CZ"); any e-INFRA CZ account can sign in.

A Talqo chat assistant widget is embedded on every page (landing, JupyterHub, and dashboard) for in-browser help.

## The five-stage workflow

Every project in MDDash is an experiment. Each experiment runs through a five-step wizard at the top of the experiment page:

1. **Setup.** Get input files into the experiment and define a *simulation manifest* (which files play which roles). A guided setup notebook in JupyterLab usually does this.
2. **Tune.** Benchmark the simulation across many execution configurations (CPU/GPU splits, MPI ranks, threads) and see measured performance (ns/day), estimated runtime, and estimated cost for the full production run. Optional. It can be skipped.
3. **Run.** Launch the production MD simulation as a cluster job with chosen parameters.
4. **Analyze.** View the trajectory in a 3D Mol* viewer and run built-in analyses (RMSD, PCA, hydrogen bonds, membrane metrics, energies, and more) as cluster jobs.
5. **Publish.** Upload the experiment to MDRepo (InvenioRDM) as a draft record that can be published with a DOI, or export to MDPosit.

Steps unlock automatically as the underlying work completes. Users can always click back to earlier steps.

## Key concepts

- **Experiment.** The top-level project unit. Users create it on the **New Experiment** page (`/new`) by picking a curated workflow card (or a custom notebooks repository) and providing a name, an MD engine (GROMACS or AMBER; fixed for the lifetime of the experiment), and initial data (a PDB structure, file upload, or a DOI/repository link).
- **Simulation manifest (`.simulation.json`).** A small JSON file inside the experiment directory that assigns *roles* to files (run input, topology, coordinates, control file, reference structure, trajectory) and holds extra engine flags. Every job uses it as the single source of truth. The setup notebook creates it, or users create it manually via the simulation form in the Setup step.
- **Jobs.** Tunings, simulations, analyses, and uploads all run as Kubernetes jobs on the cluster. They keep running even if the user closes the browser; status and logs are available on return. Statuses: PENDING, RUNNING, FINISHED, ERROR, UNKNOWN.
- **Notebook.** A per-experiment JupyterLab environment (MD workstation with GROMACS, AmberTools, NGL). Users start it on demand from the Home page, the Setup step, or the Analyze step.
- **Personal storage.** All experiment files live on a persistent personal volume and mirror continuously to S3.

## Where things are

- **Landing page (`/`).** Public overview of MDDash with **"Try MDDash"** / **"Launch MDDash"** buttons.
- **JupyterHub home (`/hub/home`).** Start and stop the personal server (the pod the whole UI runs in). It also shows server status, API tokens (`/hub/token`), and log out.
- **Dashboard Home (`/dash`).** "My Experiments" with experiment cards grouped by notebook state, plus search, sorting, and the **"New"** button. A server status bar under the header shows uptime and storage usage.
- **New Experiment (`/dash/new`).** Workflow selection with curated workflow cards grouped by engine and filterable via tabs. Each card opens the creation dialog. Own git repositories work via "Use custom workflow".
- **Experiment wizard (`/dash/experiments/<id>`).** The five-step workflow. The active step, simulation, and related state are reflected in the URL (`?step=`, `?simulation=`), so a link returns to the exact same view.
- Unknown dashboard URLs show a "Page not found" screen.
