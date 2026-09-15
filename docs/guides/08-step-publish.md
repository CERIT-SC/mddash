# Wizard Step 5: Publish

The Publish step makes experiment results publicly accessible and citable. It is an experiment-level step (wizard step 5) with the heading **"Publish your experiment (optional)"** — *"Upload the experiment's data to a public repository to make it citable, or hand it off to MDPosit."* It unlocks once a simulation job has FINISHED or an MDRepo draft/published record already exists (the Analyze step's **"Publish"** button carries the tooltip "Available once this simulation is ready to publish" while it doesn't). Two targets exist: **MDRepo** (InvenioRDM repository, default) and **MDPosit** (export-only handoff, GROMACS experiments only).

## Publishing to MDRepo

The MDRepo flow is a numbered guide: finished steps get a check mark, the step that needs you is highlighted. Once a draft exists, the dataset totals (**Files**, **Total size**) appear above the guide.

### 1. Sign-in to MDRepo (one-time authorization)

Until authenticated, the first step is open with **"First you need to sign-in with your account."** Click **"Sign-in"** — the browser is redirected through MDRepo's OAuth consent (e-INFRA CZ account) and returns to the wizard with a success toast ("Successfully authenticated with MDRepo."; failures toast "MDRepo authentication failed: …"). Tokens are stored in the session and auto-refresh; a long-idle session may need reconnecting. Sign-in stays checked once the upload has finished — a lapsed token doesn't rewind the guide, because everything after that happens MDRepo-side.

### 2. Upload your dataset

With sign-in done, the upload step opens with **"This step is going to upload your data to MDRepo server."** Clicking **"Upload"**:

1. extracts simulation metadata server-side from the topology files of every valid GROMACS simulation (`.tpr`),
2. creates an **InvenioRDM draft record** in MDRepo (reusing the existing draft when one is still there; if the draft was deleted in MDRepo, a new one is created automatically),
3. starts a background upload job (a durable Kubernetes job) that streams the experiment's files to the draft,
4. opens the **draft uploads page in MDRepo** in a new browser tab.

During upload the step shows live progress — "Upload queued. Waiting for the upload job…", then "Uploading files… (X/Y)" with a bytes line ("1 MB / 2 MB"), refreshed every 3 seconds — plus a link *"View the draft in MDRepo while files upload."*

If the draft exists but its status can't be read, the step offers *"View the draft in MDRepo."* and a **"Retry upload"** button. If the upload fails, the step shows an **"Upload failed"** alert — *"Your draft and uploaded files are preserved. Retry the upload to continue."* — with a reason line (e.g. "Authentication with MDRepo failed; reconnect to MDRepo and retry.") and the failed-files list ("N file(s) failed to upload:", up to 10 shown, then "…and N more"). Retrying resumes from the existing draft, retrying while an upload is active simply returns the running attempt, and re-publishing a completed upload is rejected with a conflict ("Upload already completed. Use MDRepo to view or edit the published record.").

### 3. Finish deposition in MDRepo

Once the upload completes, the last step opens: *"Your files are uploaded and waiting in a draft. Fill in the metadata there to publish — you don't need to come back here."* **"Finish in MDRepo"** opens the draft; reviewing metadata and minting the DOI happen inside MDRepo's own form.

### Published record

Once MDRepo reports the record as published, the guide is replaced by a **"Published"** card: the record link (with a copy button) and the dataset stats. **"Publish a new version"** is disabled — the API does not support record versioning yet. If the upload stats can't be loaded, an alert with a **Retry** button appears in their place without hiding the card.

## MDPosit handoff (GROMACS)

For GROMACS experiments, a **"Publication target"** dropdown offers "Invenio / MDRepo" (default) and "MDPosit" (AMBER experiments see no dropdown). The MDPosit target is an export helper, run as a numbered guide — preparing, downloading, and finishing are all off-platform after the first step, so the last two steps open together:

1. **Prepare the handoff package** — packages the wizard's selected simulation (switching simulation tabs clears a prepared handoff); doesn't change the experiment's publication status or wizard progress. When the simulation misses required files, a **"Handoff unavailable"** warning explains why and the button is disabled. Success toasts "MDPosit handoff files are ready."
2. **Download the handoff files** — **Metadata file (inputs.yaml)**, **Structure file**, **Topology file**, **Trajectory file**.
3. **Finish deposition in VRE Lite** — open VRE Lite, upload `inputs.yaml` first, review the imported form and fill in missing fields, then upload the structure, topology, and trajectory files.

The MDPosit target does not touch MDRepo, requires no OAuth, and does not change the experiment's publication status.
