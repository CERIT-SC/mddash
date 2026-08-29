# Wizard Step 5: Publish

The Publish step makes experiment results publicly accessible and citable. It is an experiment-level step (wizard step 5) with the heading **"Publish your experiment (optional)"** — *"Upload the experiment's data to a public repository to make it citable, or hand it off to MDPosit."* It unlocks once a simulation job has FINISHED or an MDRepo draft/published record already exists (the Analyze step's **"Publish"** button carries the tooltip "Available once this simulation is ready to publish" while it doesn't). Two targets exist: **MDRepo** (InvenioRDM repository, default) and **MDPosit** (export-only handoff, GROMACS experiments only).

## Publishing to MDRepo

### 1. Connect to MDRepo (one-time authorization)

If not yet authenticated, a yellow banner appears — **"MDRepo connection required"**: *"You need to authenticate with MDRepo to publish your experiment. This is a one-time authorization using your e-INFRA CZ account."* (when a draft already exists, the sentence reads "…to view or edit the published experiment…"). Click **"Connect to MDRepo"** — the browser is redirected through MDRepo's OAuth consent (e-INFRA CZ account) and returns to the wizard with a success toast ("Successfully authenticated with MDRepo."; failures toast "MDRepo authentication failed: …"). Tokens are stored in the session and auto-refresh; a long-idle session may need reconnecting.

### 2. Publish

Authenticated users see a **"Publish to MDRepo"** button and an info banner titled **"Publish to MDRepo"**: *"After clicking the button, you'll be redirected to MDRepo to complete the metadata and finalize the publication. Your files will be uploaded in the background."* Clicking it:

1. extracts simulation metadata server-side from the topology files of every valid GROMACS simulation (`.tpr`),
2. creates an **InvenioRDM draft record** in MDRepo (reusing the existing draft when one is still there; if the draft was deleted in MDRepo, a new one is created automatically),
3. starts a background upload job (a durable Kubernetes job) that streams the experiment's files to the draft,
4. opens the **draft uploads page in MDRepo** in a new browser tab.

### 3. Watch the upload

The step then shows:

- **Stats:** `Files:` count, `Total size:`, and an upload status chip — **"Queued"**, **"Uploading"**, **"Completed"** (green), or **"Failed"** (red).
- A **progress bar** during upload — "Upload queued — waiting for the upload job…", then "Uploading files… (X/Y)" with a bytes line ("1 MB / 2 MB"), refreshed every 3 seconds while the upload is active.
- While uploading, an **"Upload in progress"** banner notes *"Files are being uploaded to MDRepo in the background. The draft is already openable in MDRepo, but incomplete until the upload finishes."* — with a link *"View the draft in MDRepo while files upload."*

After the upload completes: green **"Upload complete"** banner — *"Your experiment data has been uploaded to the MDRepo draft. Open MDRepo to complete the metadata and finalize the publication."* — plus a **"View in MDRepo"** button. Note that "published" here means the data is uploaded into an MDRepo **draft** — the final publication step (reviewing metadata, minting the DOI) is done inside MDRepo's own form.

If the draft exists but its status can't be read, a warning banner — **"A draft exists in MDRepo"** — offers *"View the draft in MDRepo, or retry the upload to send the files again."*

If the upload fails: red **"Upload failed"** banner — *"Your draft and already-uploaded files are preserved — retry the upload to continue."* — with a reason line (e.g. "Authentication with MDRepo failed; reconnect to MDRepo and retry.", "The upload timed out; retry the upload.") and a list of failed files ("N file(s) failed to upload:", up to 10 shown, then "…and N more"). The button reads **"Retry upload"** while a draft exists; retrying resumes from the existing draft. Publishing an already-published experiment is rejected with a conflict ("Upload already completed. Use MDRepo to view or edit the published record."), and retrying while an upload is active simply returns the running attempt.

## MDPosit handoff (GROMACS)

For GROMACS experiments, a **"Publication target"** dropdown offers "Invenio / MDRepo" (default) and "MDPosit" (AMBER experiments see no dropdown). The MDPosit target is an export helper rather than an integrated publish — a **"Stateless MDPosit handoff"** banner states: *"This prepares a handoff package for the selected simulation. It does not change the experiment's publication status or wizard progress."*

The pane walks through the **"MDPosit publishing workflow"**:

1. Select the simulation to export (the wizard's selected simulation tab; switching tabs clears a prepared handoff). When the simulation is invalid or files are missing, a **"Handoff unavailable"** warning explains why and the prepare button is disabled.
2. Click **"Prepare MDPosit handoff"** ("MDPosit handoff files are ready." toast).
3. From the **"Handoff downloads"** grid, download the prepared files: **Metadata file (inputs.yaml)**, **Structure file**, **Topology file**, **Trajectory file**.
4. Click **"Open VRE Lite"** and follow the on-screen instructions: upload `inputs.yaml` first, review the imported form and fill in missing fields, then upload the structure, topology, and trajectory.

The MDPosit target does not touch MDRepo, requires no OAuth, and does not change the experiment's publication status.
