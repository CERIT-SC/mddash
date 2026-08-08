# Notebooks, Storage, and Resources

How compute and data work for a user on the MDDash production deployment.

## Notebooks (JupyterLab environments)

- Each experiment has its own **notebook** — a JupyterLab pod pre-loaded as an MD workstation (GROMACS with CUDA, AMBER `pmemd`/AmberTools, Mol* viewer, the pipeline-tracker extension). The notebooks cloned at creation (curated workflow or custom git repository) live inside the experiment directory.
- Notebooks are started on demand from the **Setup** or **Analyze** step's notebook controller: pick a **Size** tier from the offered list (each tier is shown with its CPU/RAM, e.g. `1x · N cores / M GB`; larger tiers get proportionally more) and optionally tick the **GPU** checkbox, then **Start**.
- The **Open** button lands directly in the experiment's `setup.ipynb` (Setup step) or `analysis.ipynb` (Analyze step) inside JupyterLab, in a new tab. **Stop** shuts the notebook down; on errors a yellow **Respawn** button restarts it.
- **Limits:** the number of concurrent notebooks per user is capped — exceeding the cap shows a toast "Maximum of N concurrent notebook(s) reached. Stop one first." If the user's namespace has no quota headroom, a "Resource quota exceeded..." toast appears. On deployments without GPU support, starting with GPU shows "GPU acceleration isn't enabled here...".
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
- **Not everything is mirrored:** large raw MD outputs are excluded from S3 and stay volume-local — `*.edr`, `*.xtc`, `*.tpr`, `*.cpt`, `*.gro`, `*.log`, plus caches (`.git`, `__pycache__`, `.binder-env`, notebook checkpoints, analysis scratch dirs). Consequence: S3 is a convenience mirror for sources and small artifacts, **not** a backup of trajectories — the volume itself is the durable store.
- Empty directories are never deleted nor created on S3.
- A `.s3-init` marker file exists in the home directory — do not delete it; it keeps the sync safe on fresh volumes.
- Files created in JupyterLab can take a sync cycle (~10 s) to become visible to other parts of the system — if a brand-new file seems missing from a file picker, wait a few seconds.

## Resource limits

MDDash enforces per-user resource limits (CPU, memory, storage, concurrency) whose exact values are configured per deployment. What users experience:

- **Home → Resource Usage** shows the current CPU / Memory / Storage consumption against the user's quota, refreshed periodically.
- **Concurrency is capped:** notebook pods are limited (exceeding shows "Maximum of N concurrent notebook(s) reached"), the number of production simulation jobs a user can run concurrently is limited, and one analysis job runs per experiment at a time.
- Hitting quota shows a "Resource quota exceeded..." toast when starting notebooks or jobs.

Practical implications: run experiments serially — one production job, one notebook. Stop the notebook when done to free quota. Deleting old experiments frees both storage and quota headroom.
