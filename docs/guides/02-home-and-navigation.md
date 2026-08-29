# Dashboard Home Page and Navigation

The Home page (`/dash`, route `/`) is the landing view after the server starts. Its single section is **My Experiments**; a server status bar sits directly under the header.

## Global page shell

Every dashboard page shares the same chrome:

- **Header** (e-INFRA design system):
  - Left: e-INFRA CZ logo and the **"MDDash"** label, both linking back to the Home page.
  - Left, next to the logo: navigation links **"Home"** (JupyterHub home at `/hub/home` — server control) and **"Get Token"** (`/hub/token` — JupyterHub API tokens).
  - Right: **theme toggle** (Sun/Moon icon) switching light/dark mode, the **username**, and a **"Log out"** button.
- **Status bar** attached below the header (hidden on experiment pages, where a notebook bar takes its place — see the step guides):
  - **"Server"** — a green dot plus the server's live uptime (ticking every second).
  - **"Storage"** — `used / limit` (e.g. `40.8 GB / 100.0 GB`) with a usage bar; shows **"Unavailable"** while usage cannot be measured. This is the only quota display in the dashboard — there are no CPU/memory cards.
  - **"Stop server"** (red outline) — opens a confirmation dialog ("Stop this server? Any unsaved notebook state will be lost…") with **"Keep running"** / **"Stop server"**. Confirming routes to `/hub/home?stop`, where the hub performs the stop and shows its stopping page.
- Notifications appear as toasts at the top-center of the screen (e.g. `Experiment "…" created`, quota errors). Error toasts show the actionable message sent by the backend when available.
- There is no footer.

Routes: `/` (Home), `/new` (New Experiment — workflow selection; the engine filter lives in the URL as `?engine=`), and `/experiments/<id>` (experiment Wizard). Unknown paths show a **"Page not found"** screen. There is no settings page and no user profile page.

## My Experiments

The heading row pairs the **"My Experiments"** title with the **"New"** button that opens the New Experiment page (see "Getting Started").

Above the card grid, a toolbar offers:

- **"Search experiments"** input — filters cards by name (reflected in the URL as `?q=`).
- A sort dropdown — **"Newest first"** / **"Oldest first"** (URL `?sort=oldest`).
- **"Active"** / **"Archived"** tabs — Archived is a placeholder and cannot be selected yet.

Cards are grouped under two headings: **"Notebook running"** (with a count badge; shows `N/M` when the deployment's notebook concurrency limit is known) and **"Notebook stopped"**. While loading, skeleton cards are shown; with no experiments the page reads "No experiments yet.", and an empty search result reads "No experiments match …". Load failures render a durable error alert with a **"Retry"** button.

Each experiment card represents one experiment and shows:

- A **step icon tile** (flask/sliders/rocket/pulse/award) reflecting the experiment's current workflow step.
- The **name** (the whole card links to the wizard) and a subtitle `<workflow module or "Custom"> · <GROMACS|AMBER>`.
- A step line like **"Tune · 2 of 5"** plus a status line: "Active 12 min ago" when idle, or the live phase ("Simulating · 34%", "Tuning", "Analyzing", "Publishing") with a spinner while work is in flight.
- A **five-segment progress ladder** (one segment per workflow step; filled = completed, tinted = current).
- **Step-specific details**, e.g. Setup: "Setup ready" + "Workflow"; Tune: "Configurations — N of M explored" + "Steps"; Run: "Time remaining" + "Steps"; Analyze: "Models" + "Analyses — N of M ready"; Publish: "Published" Yes/No + "Target".
- A footer with the **source label** (e.g. "RCSB PDB (1BNA)", "Uploaded 2 files", or the notebooks repository), the **size** of the experiment data, and a **Notebook** indicator (green dot = notebook running, grey = stopped).

Card actions live in the **⋯ (ellipsis) menu** (tooltip "Actions for <name>"):

- **Rename** — opens a "Rename experiment" dialog with a Name field and **Cancel** / **Save**.
- **Duplicate** — shown but disabled (not yet available).
- **Start notebook** / **Stop notebook** — controls the experiment's notebook from the Home page. Starting when the per-user notebook limit is reached opens the **"Notebook limit reached"** dialog (list the running notebooks, stop one, then **"Start new notebook"**).
- **Archive** — shown but disabled (not yet available).
- **Delete** — opens `Delete experiment "<name>"?` listing exactly what is removed ("All simulation files and results (X GB)", "The experiment's notebook" when present, "N running or queued job(s)" when any) and stating "This can't be undone." An info block offers **"Archive instead"** (to keep results) — currently disabled. Confirm with **"Delete experiment"** or **"Cancel"**. Deletion is permanent.

There is no pagination and no bulk actions.
