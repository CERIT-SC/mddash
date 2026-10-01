# Architecture

![Architecture Diagram](img/architecture.png)

## Admin namespace

Shared infrastructure that manages the platform and compute resources.

- **JupyterHub.** `hub/` (custom `mddash-hub` image: stock `k8s-hub` + EGI Check-in authenticator + MDDash-branded hub UI in `hub/ui/`, one HTML entry per JupyterHub template), configured in `helm/charts/mddash/values.yaml.tmpl`. Manages user logins and spawns an isolated environment per user on demand.
- **MDRun API.** `mdrun-api/`, `helm/charts/mdrun-api`. Decouples simulation execution from user sessions, so long-running GROMACS and AMBER jobs continue if the user logs out.
- **Tuner.** `tuner/`, `helm/charts/tuner`. Benchmarks and selects the most efficient execution parameters (MPI ranks, OpenMP threads, GPU assignment).
- **Landing page.** `landing/`. Public page served at the root path, linking to the JupyterHub login at `/hub/`.

## User namespace

Isolated environment created for each logged-in user. All containers share a PVC mounted at `/mddash`.

- **Proxy (Caddy).** `dashboard/proxy/`, ports `8888` and `2019` (admin). Single entry point for the user pod; routes traffic to the UI, API, or Jupyter, and serves the compiled frontend.
- **JupyterHub Singleuser.** Configured in `helm/charts/mddash/values.yaml.tmpl`, port `8080`. Standard interface JupyterHub uses to manage the pod's lifecycle.
- **Forward auth.** `dashboard/auth/`, port `5001`. Validates JupyterHub sessions before requests reach the API or UI.
- **UI.** `dashboard/ui/`. Graphical interface for experiment setup, monitoring, and the five-step wizard.
- **API.** `dashboard/api/`, port `5000`. Business logic: experiment state, and coordination between the UI and the simulation services.
- **S3 sync daemon.** `dashboard/s3-sync/`. Continuously syncs user data between the PVC and S3 (`rclone bisync`).
- **Analysis job.** Executed from `dashboard/api/models/analysis_job.py`. Runs on-demand analysis jobs against experiment data.
- **Jupyter notebooks.** `notebook/`. Interactive environment for setup tasks that need manual visualization or intervention.
- **User PVC.** Configured in `helm/charts/mddash/files/pre_spawn_hook.py`. Persists `/mddash` across sessions.

## External services

- **S3.** External `s3.endpoint` or the bundled SeaweedFS store (`s3.seaweedfs.enabled` in `config*.yaml`); credentials in `${PACKAGE}-s3-creds`. Persistent storage for large simulation datasets and trajectories.
- **MDRepo.** InvenioRDM-based repository where completed experiments are published. Endpoint and OAuth client in `config*.yaml` (`mdrepo:`, secrets in `${PACKAGE}-mdrepo-credentials`); OAuth flow managed by the Dashboard API.
