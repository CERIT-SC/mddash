# MDDash User Guides

User-facing documentation for the MDDash production deployment. Suitable as context for RAG pipelines: each file covers one topic with verbatim UI labels. Deliberately excludes deployment-configurable values (quota numbers, URLs, timeouts) that may change over time — guides describe durable behavior and UI structure only.

| File | Topic |
|---|---|
| `00-overview.md` | What MDDash is, the five-stage workflow, core concepts (experiments, simulation manifests, jobs, notebooks, storage) |
| `01-getting-started.md` | Landing page, e-INFRA CZ login, JupyterHub home, starting the personal server, creating the first experiment |
| `02-home-and-navigation.md` | Dashboard Home page (My Experiments cards, Resource Usage), header/footer, global navigation |
| `03-wizard-mechanics.md` | The experiment wizard: stepper, step unlocking rules, simulation tabs |
| `04-step-setup.md` | Step 1 Setup: setup notebook, creating/editing simulations, the `.simulation.json` manifest, file roles, locking |
| `05-step-tune.md` | Step 2 Tune: benchmarking trials, performance/cost estimates, badges, skipping tuning |
| `06-step-run.md` | Step 3 Run: GROMACS/AMBER start forms, job lifecycle, progress, logs |
| `07-step-analyze.md` | Step 4 Analyze: Mol* 3D viewer, built-in analyses catalogue, preprocessing |
| `08-step-publish.md` | Step 5 Publish: MDRepo OAuth, draft upload and statuses, MDPosit handoff |
| `09-notebooks-storage-resources.md` | Notebook tiers and quotas, personal storage/S3 sync behavior, production resource limits |
| `10-faq-troubleshooting.md` | Frequently asked questions, common errors and their fixes, glossary |
