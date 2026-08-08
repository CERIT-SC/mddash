# Wizard Step 5: Publish

The Publish step ("Publish Experiment") makes experiment results publicly accessible and citable. Two targets exist: **MDRepo** (InvenioRDM repository, default — creates a draft record with a DOI on final publication) and **MDPosit** (export-only handoff for GROMACS experiments).

## Publishing to MDRepo

### 1. Connect to MDRepo (one-time authorization)

If not yet authenticated, a yellow banner appears: *"You need to authenticate with MDRepo to publish your experiment. This is a one-time authorization using your e-INFRA CZ account."* Click **"Connect to MDRepo"** — the browser is redirected through MDRepo's OAuth consent (e-INFRA CZ account) and returns to the wizard with a success toast ("Successfully authenticated with MDRepo!"). Tokens are stored in the session and auto-refresh; a long-idle session may need reconnecting.

### 2. Publish

Authenticated users see a **"Publish to MDRepo"** button and an info banner: *"Publishing will upload your experiment data to MDRepo, making it publicly accessible and citable with a DOI."* Clicking it:

1. extracts simulation metadata from the experiment's files server-side (for GROMACS, from `.tpr` files),
2. creates an **InvenioRDM draft record** in MDRepo,
3. starts a background upload job that streams the experiment's files to the draft,
4. opens the **draft edit page in MDRepo** in a new browser tab.

### 3. Watch the upload

The step then shows:

- **Stats:** Files count, Total Size, and an upload Status chip — QUEUED (yellow), RUNNING (yellow with spinner), COMPLETED (green), FAILED (red).
- A **progress bar** during upload — "Upload queued, waiting for pod...", then "Uploading files... (X/Y)" with percentage and bytes transferred, refreshed every 3 seconds.
- While uploading, a yellow banner notes *"Files are being uploaded to MDRepo in the background. The draft is openable but incomplete."* with a link *"View the draft in MDRepo while files upload."*

After the upload completes: green banner *"Upload complete. Your experiment data has been published to MDRepo."* and a **"View in MDRepo"** button. Note that "published" here means the data is uploaded into an MDRepo **draft** — the final publication step (reviewing metadata, minting the DOI) is done inside MDRepo's own draft form.

If the upload fails: red banner *"Upload failed. You can retry the publication — your draft and already-uploaded files are preserved."*, plus a list of failed files (up to 10 shown). The button reads **"Retry Upload"** while a draft exists; retrying resumes from the existing draft. Re-publishing an already-published record is rejected by MDRepo.

## MDPosit handoff (GROMACS)

For GROMACS experiments, a **"Publication target"** dropdown offers "Invenio / MDRepo" (default) and "MDPosit". The MDPosit target is an export helper rather than an integrated publish:

1. Select the simulation to export.
2. Click **"Prepare MDPosit handoff"**.
3. From the "Handoff downloads" grid, download the prepared files: **Metadata file (inputs.yaml)**, **Structure file**, **Topology file**, **Trajectory file**.
4. Click **"Open VRE Lite"** and follow the on-screen instructions: upload `inputs.yaml` first, fill in missing metadata fields, then upload the structure, topology, and trajectory.

The MDPosit target does not touch MDRepo, requires no OAuth, and does not change the experiment's publication status.
