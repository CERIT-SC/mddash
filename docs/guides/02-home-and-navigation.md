# Dashboard Home Page and Navigation

The Home page (`/dash`, route `/`) is the landing view after the server starts. It has three stacked sections: **My Experiments**, **Resource Usage**, and **Documentation**.

## Global page shell

Every dashboard page shares the same chrome:

- **Header** (primary-colored bar):
  - Left: **house icon** — tooltip "Back to JupyterHub", links to `/hub/home` (server control and logout live there).
  - Left (on any non-home page): a **"Back to Dashboard"** arrow button.
  - Center: **"MDDash"** title — links back to the Home page.
  - Right: **theme toggle** (Sun/Moon icon) switching light/dark mode.
- **Footer**: a single centered "MDDash" line.
- Notifications appear as toasts at the top-center of the screen (e.g. "Experiment created successfully!", quota errors). Error toasts show the actionable message sent by the backend when available.

Routes: `/` (Home), `/new` (New Experiment), `/<id>/wizard` (experiment Wizard). There is no settings page and no user profile page.

## My Experiments

A responsive card grid (1–4 columns depending on width). Each card represents one experiment and shows:

- **Name**
- **Step:** the current wizard step
- **Status:** the experiment status
- **Notebook:** a status chip of the experiment's notebook pod (green RUNNING; yellow with spinner PENDING / INITIALIZING / TERMINATING; blue TERMINATED; red DOWN / ERROR; grey UNKNOWN)
- **Tuner jobs:** count
- **Simulation jobs:** count

Card actions:

- **Wizard** (wand icon) — opens the experiment wizard at `/<id>/wizard`.
- **Delete** (red outline, trash icon) — opens a confirmation dialog: *"Are you sure you want to delete this experiment? All data will be lost."* with **Cancel** / **Confirm** buttons. Deletion is permanent.

The last card is a dashed **"+ New"** tile linking to the New Experiment form. Notes: there is no search/filter, no pagination, no bulk actions, and no rename on this page — renaming an experiment is done inside the wizard (pencil icon next to the experiment name).

## Resource Usage

Three cards showing the user's namespace quota allocation, refreshed every 30 seconds:

- **CPU** — "X.XX / Y.YY cores" and "% allocated" (blue bar, turns yellow above 80%).
- **Memory** — "X.XX / Y.YY GB" and "% allocated" (yellow bar, turns red above 80%).
- **Storage** — "X.XX / Y.YY GB" and "% used" (green bar, turns red above 80%). While usage is being computed, it shows **"Calculating..."** with a pulsing bar and "N/A" values.

These show Kubernetes quota *requests/limits* (allocation against the user's quota), not live second-by-second consumption. The actual quota numbers are deployment-configured — see Home → Resource Usage for current values.

## Documentation

Currently a placeholder reading *"There is no documentation yet :P"* — user documentation is maintained outside the app.
