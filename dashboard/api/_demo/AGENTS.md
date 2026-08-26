# MDDash API — Local Demo

`make demo` runs `dashboard/api/_demo/app.py` (the real API with mocked integrations) next to the React dev server. Demo state lives in `/tmp/mddash` (`MDDASH_DEMO_DATA_DIR`) and is **wiped on every start**, including debug-reload restarts — `seed_data()` is the only seeding path, and UI mutations intentionally never survive a restart.

Gotchas the code does not make obvious:

- Mocks must be installed **before** the app import in `app.py`, and K8s is mocked by mutating `clients.k8s` functions, not by patching the `kubernetes` lib (`load_incluster_config` is lazy, so library-side patching does nothing).
- Analysis results are file-first, like production: calculate → fetch the MDPosit payload → write `mda.*` files where an mwf run would leave them → the real routes read the filesystem. Nothing is injected above the API. Seeded FINISHED analyses materialize their files at seed time; seeded RUNNING ones and user-submitted mock jobs finish via `complete_analysis_with_mdposit` on a daemon thread — never hand-write result files for them.
- The MDPosit fetch is a deliberate network exception: the `responses` mock layer passes `*/analyses/*` (incl. the redirect target) to the real server, because vendored fixtures go stale against mwf format changes. Source project `MD-A003ZT.2` is a membrane-protein run so all lipid analyses exist; `pockets` 404s there, so a submitted pockets job ends ERROR like a real failed run. Payloads cache to `~/.cache/mddash-demo/` (`MDDASH_DEMO_ANALYSIS_CACHE`) — `rm -rf` that dir to force refetches.
- Running GMX/AMBER jobs show live progress: each status poll appends log lines from `_demo/data/md.log`. Logs are written lazily on the first poll because `Job.start()` cleans result files after submit.
- The seeded running tuner never finishes on purpose: it keeps a rolling window of `max_trials` trials (oldest dropped), and FINISH/ERROR alternates by trial creation `seq` — not list index, which the rolling window would pin to constant parity.
- Placeholder enzyme manifests are back-dated (`_backdate_stale_simulations`) so the job-linked `md` simulation stays the experiment's most recent activity; equal mtimes would pick the alphabetically-first manifest and drive the wrong step.
- `/mdrepo/auth` bypasses OAuth with a demo session token; the upload "Job" is a mock K8s thread writing the completed status after ~4s.
