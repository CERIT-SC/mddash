# Getting started with login, server and dashboard

This guide covers everything before the first experiment: reaching MDDash, signing in, starting the personal server, and creating an experiment.

## Landing page

The MDDash root URL shows the public landing page: an overview of the five-stage workflow (Setup, Tune, Run, Analyze, Publish), platform capabilities, and a **"Try MDDash"** / **"Launch MDDash"** button that starts the sign-in flow. No account is needed to view this page.

## Signing in

Login is a single button: **"Sign in with e-INFRA CZ"**. MDDash uses e-INFRA CZ single sign-on (OpenID Connect); any e-INFRA CZ account can sign in.

## JupyterHub home and the personal server

After login the browser lands on **JupyterHub home** (`/hub/home`). It shows one status hero. **"Your server is running"** offers **"Open my server"** and a red **"Stop my server"** button. **"Your server is offline"** offers **"Start my server"**. **"Starting your server…"** / **"Stopping your server…"** shows while the pod transitions. Stopping the server keeps all data; running cluster jobs continue.

**First startup** provisions the personal namespace, storage, and S3 bucket and streams progress with a percentage bar and the current step: "Creating user namespace…", "Waiting for namespace to be ready…", "Setting up access controls…", "Waiting for resource quota…", "Starting sidecar containers…", "Waiting for MDDash to start…". Startup can take a couple of minutes, and the page offers a **"Cancel startup"** button. If spawning fails, a **"Failed to start your server"** page appears with a **"Try again"** button and an expandable event log.

The top navigation offers **Home**, **Get Token** (JupyterHub API tokens), a theme toggle, the username, and **Log out**. The MDDash dashboard header repeats the theme toggle, username, and a **Log out** button, so logging out works from both places.

## Landing in the dashboard

When the server starts, the browser goes to the **MDDash dashboard Home page** (`/dash`), not to JupyterLab. The pod routes are:

- `/dash` for the React dashboard (Home and the experiment wizard).
- everything else for JupyterLab / the notebook server.

## Creating the first experiment

On the dashboard Home page, click the **"New"** button next to the "My Experiments" heading. It opens the **New Experiment** page (`/dash/new`):

1. **Pick a workflow.** The page shows "Select a Workflow" with *"A workflow is a set of notebooks that prepares and runs your simulation. Start from a curated one, or bring your own git repository."* It shows curated workflow cards grouped under **GROMACS** and **AMBER** headings, with an **All / GROMACS / AMBER** filter tab (reflected in the URL as `?engine=`). Each card shows an icon for its simulation category, the workflow **name**, a `<Category> · <engine>` subtitle (e.g. "Protein · GROMACS"), a short description, and the **author**. Choosing a curated workflow fixes the MD engine.
2. **Or go custom.** The **"Use custom workflow"** button (top right) creates an experiment from any git repository with notebooks and lets you pick the engine.
3. **Fill the form.** Clicking a card (or "Use custom workflow") opens the creation dialog on top of the page, titled **"New Experiment: \<workflow name\>"** (or "Custom workflow"). It asks for:
   - **Name.** Free text (required), placeholder "Enter the name of the experiment".
   - **MD engine.** GROMACS or AMBER toggle (custom only; fixed for the lifetime of the experiment).
   - **Initial data.** A toggle with three mutually exclusive sources (default **PDB**):
     - **PDB.** Field "PDB ID or URL": an RCSB PDB ID (e.g. `1ABC`) or a direct URL to a `.pdb` file; MDDash downloads the structure from RCSB PDB.
     - **Upload files.** Drag-and-drop or click the dropzone ("Drop files here or click to browse"). Selected files are listed with name and size. Use this to bring existing `.tpr`/`.gro`/`.prmtop`/`.inpcrd`/`.mdin` files.
     - **DOI / repository.** Field "DOI or Repository URL": a DOI link or a URL of any InvenioRDM repository (Zenodo, MDRepo) to import data from.
   - **Notebooks repository** (custom only). A git URL for the workflow notebooks, prefilled with the deployment's default repository. It supports Binder-compatible and standard repos. For private HTTPS repositories, expand **"Private repository? Provide an access token"** and paste a git token. MDDash uses it only for cloning and does not store it (SSH-style URLs hide this field).
4. Click **"Create Experiment"**. Missing required fields show inline messages under each field (e.g. "Enter a name for the experiment", "Add at least one file").

On success the dialog closes with the toast `Experiment "…" created` and the browser navigates into the new experiment's **wizard**. The selected notebooks repository is cloned into the experiment directory and the input data is fetched.

## What new users should know

- Running jobs (tuning, simulations, analyses) survive logout and server restarts. Close the browser any time and come back later.
- Files live on a persistent personal volume; MDDash also mirrors them to S3 automatically about every 10 seconds (with exceptions. Large trajectory/output files are *not* synced to S3; see "Notebooks, Storage and Resources").
- A **concurrent notebook limit** applies per user. Starting another notebook when the limit is reached opens a **"Notebook limit reached"** dialog listing the running notebooks with **Open** / **Stop** buttons and a **"Start new notebook"** action. Stop one to free a slot.
- Notebooks shut down automatically after a period of inactivity to free resources; files on disk are unaffected.
- The dashboard header's **"Home"** link returns to JupyterHub home for server control; the server status bar's **"Stop server"** button (with confirmation) does the same.
