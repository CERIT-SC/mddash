# MDDash API — Local Demo

`make demo` runs `dashboard/api/_demo/app.py`: the real dashboard API with mocked integrations and seeded data, next to the React dev server.

## Structure

- Mocks are applied before app import in `app.py` — this ordering matters; seeding/mocks live in `_demo/profile.py`.
- K8s is mocked by mutating `clients.k8s` functions (not by patching the `kubernetes` lib — `load_incluster_config` is lazy, so patching the library class before import does nothing). `check_quota_headroom`, `count_notebook_pods`, `read_job`, `wait_for_pod_admission` etc. are all neutralized in `_demo/mocks/k8s.py`.

## Persistence & Reset

- Demo state lives at `MDDASH_DEMO_DATA_DIR` (default `/tmp/mddash`) and is wiped on every app start — including debug-reload restarts (parent + child) — so the UI always starts pristine and `seed_data()` is the only seeding path. Mutations made through the demo UI (renames, deletions, …) intentionally never survive a restart. There is no rehydration path to keep in sync with the seed.
- The placeholder enzyme manifests are back-dated by the seed (`_backdate_stale_simulations()`) so the job-linked `md` simulation stays the experiment's most recent activity and drives its step (identical mtimes from the tight write loop would otherwise pick the alphabetically-first manifest).

## Live Job Simulation

- Running jobs show live progress: each mdrun status poll appends GMX log lines from `_demo/data/md.log` (deffnm = run_input minus `.tpr`, step table advances over the whole run, perf-summary/`Finished mdrun` tail appended only on completion; `Started/Finished mdrun` dates are stamped at write time) and rewrites the AMBER `.mdinfo` Nstep. Job logs/stdio are written lazily on first status poll because `Job.start()` cleans result files after submit.
- The seeded running tuner rolls forever: the mock keeps a rolling window of `max_trials` trials (dropping the oldest) instead of reaching FINISHED, so sustained polling never burns it out; FINISH/ERROR alternates by each trial's creation `seq`, not its list index (the window would otherwise pin every new trial to the same odd index). The seeded stopped NPT tuner covers the finished-state UI.
- Which seeded analyses stay RUNNING is defined in `RUNNING_SEEDED_ANALYSIS_IDS`; their `demo_state` entries carry `created_at` like the `_create_job` mock — without it the status flip-flops ERROR→FINISHED on poll because no result files are written for them.
- MDRepo publish is fully simulated: `/mdrepo/auth` bypasses OAuth with a demo session token; the upload "Job" is a mock K8s worker thread that writes a `completed` upload-status file after ~4s.
