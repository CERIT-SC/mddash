# Getting Started: Login, Server, Dashboard

This guide covers everything before the first experiment: reaching MDDash, signing in, starting the personal server, and creating an experiment.

## Landing page

The MDDash root URL shows the public landing page: an overview of the five-stage workflow (Setup, Tune, Run, Analyze, Publish), platform capabilities, and a **"Try MDDash"** / **"Launch MDDash"** button that starts the sign-in flow. No account is needed to view this page.

## Signing in

Login is a single button: **"Sign in with e-INFRA CZ"**. MDDash uses e-INFRA CZ single sign-on (OpenID Connect). New users must first contact the MDDash team for a lightweight registration (to ensure hardware is used according to the AUP); afterwards, any e-INFRA CZ account can sign in.

## JupyterHub home and the personal server

After login the browser lands on **JupyterHub home** (`/hub/home`). It shows one card, **"My server"**, describing the user's personal computing pod, with a status badge (Running / Starting… / Stopping… / Stopped) and buttons:

- **Start my server** — provisions/starts the personal pod.
- **Open my server** — enters the running environment.
- **Stop my server** — shuts the pod down (data persists; running cluster jobs continue).

The top navigation offers **Home**, **Tokens** (JupyterHub API tokens), **Admin** (admins only), and the username with **Log out**. Note: the MDDash dashboard itself has no logout button — logging out happens here on the JupyterHub home (reachable any time via the house icon in the dashboard header).

**First startup** provisions the personal namespace, storage, and S3 bucket and streams progress: "Creating user namespace…", "Waiting for namespace to be ready…", "Setting up access controls…", "Waiting for resource quota…", "Starting sidecar containers…", "Waiting for MDDash to start…". Startup can take a couple of minutes. If spawning fails or times out, a "Spawn failed" page with a Relaunch button appears.

## Landing in the dashboard

When the server starts, the browser is taken straight to the **MDDash dashboard Home page** (`/dash`) — not to JupyterLab. The pod routes are:

- `/dash` — the React dashboard (Home, New experiment, Wizard).
- everything else — JupyterLab / the notebook server.

## Creating the first experiment

On the dashboard Home page, click the dashed **"+ New"** card at the end of the experiments grid (goes to `/new`). The "New Experiment" form asks for:

1. **Name** — free text (required).
2. **MD Engine** — tabs: **GROMACS** or **AMBER** (fixed for the lifetime of the experiment).
3. **Initial Data** — tabs with three mutually exclusive sources:
   - **Upload Files** — drag-and-drop or click the dropzone ("Drop files here or click."). Selected files are listed with name, size, and a trash button. Use this to bring existing `.tpr`/`.gro`/`.prmtop`/`.inpcrd`/`.mdin` files.
   - **PDB** — an RCSB PDB ID (e.g. `1ABC`) or a direct URL to a PDB file.
   - **DOI / Repository** — a DOI link or a URL of any InvenioRDM repository (Zenodo, MDRepo) to import data from.
4. **Notebook Workflow** — pick one of the curated workflow notebooks shown for the chosen engine (click a card to select it), or click **"Use custom notebooks repository"** to provide any git URL (Binder-compatible repos supported). For private HTTPS repos, expand **"Provide access token"** and paste a git token — it is used only for cloning and is not stored. **"Back to curated workflows"** returns to the module list.
5. **Create Experiment** — submits the form. Missing required fields highlight in red and a toast "Please fill in all required fields" appears.

On success the browser navigates to the experiment **Wizard**. Behind the scenes, the selected notebooks repository is cloned into the experiment directory and the input data is fetched.

## What new users should know

- Running jobs (tuning, simulations, analyses) survive logout and server restarts — close the browser any time and come back later.
- Files live on a persistent personal volume; they are also mirrored to S3 automatically about every 10 seconds (with exceptions — large trajectory/output files are *not* synced to S3; see "Notebooks, Storage and Resources").
- There is a **concurrent notebook limit** per user (starting another shows a "Maximum of N concurrent notebook(s) reached" toast); stop one notebook before starting another.
- Notebooks shut down automatically after a period of inactivity to free resources; files on disk are unaffected.
- The dashboard header's house icon (top-left, tooltip "Back to JupyterHub") always returns to JupyterHub home for server control and logout.
