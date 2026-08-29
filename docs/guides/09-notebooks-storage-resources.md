# Notebooks, Storage, and Resources

How compute and data work for a user on the MDDash production deployment.

## Notebooks (JupyterLab environments)

- Each experiment has its own **notebook** — a JupyterLab pod pre-loaded as an MD workstation (GROMACS with CUDA, AMBER `pmemd`/AmberTools, the NGL viewer, the pipeline-tracker extension). The notebooks cloned at creation (curated workflow or custom git repository) live inside the experiment directory.
- Notebooks are started on demand from the **Setup** or **Analyze** step (or from the Home page card menu's **"Start notebook"**): pick a **Size** tier from the offered list (each option is shown as its resources, e.g. `5 cores / 8 GB`; larger tiers get proportionally more) and optionally tick the **GPU** checkbox, then **"Start notebook"**.
- The **"Open notebook"** button lands directly in the experiment's `setup.ipynb` (Setup step) or `analysis.ipynb` (Analyze step) inside JupyterLab, in a new tab. **"Stop notebook"** shuts the notebook down; on errors the start form simply reappears — start it again. While a notebook is running, a notebook status bar with the same controls appears under the header on every experiment page, tracking **"Starting…"**, **"Initializing…"**, "Taking longer than expected", the live uptime, or **"Stopping…"**.
- **Limits:** the number of concurrent notebooks per user is capped. Starting another when the limit is reached opens the **"Notebook limit reached"** dialog listing the running notebooks with Open/Stop buttons and a **"Start new notebook"** action once a slot frees. If the user's namespace has no quota headroom, an error toast appears (e.g. "Memory quota would be exceeded: …", "Resource quota exceeded. Please stop other notebooks."). On deployments without GPU support, starting with GPU shows "GPU acceleration isn't enabled here; start the notebook without GPU."
- **Idle timeout:** notebooks shut down automatically after a period of inactivity (kernel culled, pod stopped) to free resources. Data on disk is not affected.

## Where files live

- Everything for an experiment lives in `/mddash/<experiment_id>/` on the user's **personal persistent volume**, mounted into every container — the dashboard, JupyterLab, notebook pods, and job pods all see the same files.
- The volume survives server stops, pod restarts, and logout. It is the primary persistence guarantee.
- In JupyterLab, the experiment directory appears directly in the file browser; writing from the notebook is the normal way to modify inputs.

## S3 synchronization (automatic)

An always-on background sidecar continuously mirrors `/mddash` to a personal S3 bucket (roughly every 10 seconds) using bidirectional sync:

- **Deletions propagate both ways.** Deleting a file in JupyterLab deletes it from S3, and vice versa. There is no recycle bin — assume deletion is permanent.
- On sync conflicts, the **newer version** of a file wins.
- A final sync runs on pod shutdown so nothing is lost when the server stops.
- **Not everything is mirrored:** large raw MD outputs are excluded from S3 and stay volume-local — `*.edr`, `*.xtc`, `*.tpr`, `*.cpt`, `*.gro`, `*.log` (including fitted `*.fit.xtc`) — plus caches and tool state (`.git`, `__pycache__`, `.binder-env`, notebook checkpoints, analysis scratch dirs, `.cache`/`.local`/`.config`, and more). Consequence: S3 is a convenience mirror for sources and small artifacts, **not** a backup of trajectories — the volume itself is the durable store.
- Empty directories are never deleted nor created on S3.
- A `.s3-init` marker file exists in the home directory — do not delete it; it keeps the sync safe on fresh volumes.
- The dashboard's file pickers read the volume directly, but the UI polls on a cadence of a few seconds — a brand-new file can take a moment to appear in a picker or the wizard; retry shortly if one seems missing.

## Resource limits

MDDash enforces per-user resource limits (CPU, memory, storage, concurrency) whose exact values are configured per deployment. What users experience:

- The **server status bar** under the dashboard header shows the storage usage against the personal volume's size ("Storage: X / Y" with a usage bar). There is no CPU/memory usage display.
- **Concurrency is capped:** concurrent notebooks per user are limited (the Home page groups cards under "Notebook running" with a `count/limit` badge), and one analysis job runs per simulation at a time (submitting a new one for a simulation replaces the previous one). There is no fixed per-user count limit on production simulation jobs — those are bounded by the namespace's CPU/memory quota, and jobs that exceed it simply stay queued (PENDING) until resources free up.
- Hitting namespace quota when starting a notebook shows an error toast ("Resource quota exceeded. Please stop other notebooks." or a dynamic "Memory quota would be exceeded: …" message).

Practical implications: run experiments serially — one production job, one notebook. Stop the notebook when done to free quota. Deleting old experiments frees both storage and quota headroom.
