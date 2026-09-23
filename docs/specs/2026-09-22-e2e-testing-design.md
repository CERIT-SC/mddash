# E2E Testing Design

Date: 2026-09-22
Status: implemented

## Problem

MDDash cannot be fully deployed locally: the platform depends on Rancher-provisioned Kubernetes (per-user namespaces, project annotations, ResourceQuota), JupyterHub spawning, EGI Check-in SSO, S3 sync via rclone sidecar, and external MDRepo. There is no end-to-end regression protection for user flows; unit/component tests per service are the only automated checks.

## Constraints

- **No production-code changes to accommodate tests.** UI poll intervals, runtime config shape, and all shipped behavior stay untouched. All test-support changes are confined to `dashboard/api/_demo/**` (the demo harness), the new `e2e/` package, and root-level tooling configuration (package.json scripts, pnpm-workspace.yaml, .gitignore, dependabot, devcontainer, workflows).
- **One mode switch only.** A single `MDDASH_DEMO_E2E=1` environment variable selects compressed-timing behavior in the demo harness; constants are hardcoded in the demo layer, not configurable.
- **UI must traverse the same states as in production** (e.g. RUNNING with growing progress, in-progress publish, stopping). Speed comes from accelerating transitions, never from injecting end states into the UI.
- **Simplicity over hedging.** No page-object models, no helper layers, no assertion wrappers; a shared helper exists only once ≥2 specs need it. Comments only for non-obvious invariants. Demo-harness changes are inline hardcoded branches on the `E2E` flag. Where a faster configuration carries a known, nameable risk, the spec documents the wind-back lever instead of pre-mitigating.

## Goals

- Browser-level E2E covering the critical user journeys of the dashboard, runnable locally via `make e2e` and as a manually triggered GitHub Actions workflow.
- Deterministic: no live network, no fixed sleeps anywhere, seeded state reset per run.
- Fast: suite in the low single-digit minutes, parallel across 3 workers.

## Non-goals

- Full-platform deployment tests (kind + simulated Rancher): rejected — the pre-spawn hook hard-depends on Rancher CRDs/controllers; simulation cost is high, signal low, and `_deploy.yml` health verification already covers deploy health.
- Compose-based user-pod harness (proxy/auth/s3-sync with stub OAuth/MinIO): rejected — a second, drifting deployment description.
- SSO/login flows, chaos/soak testing, infra failure modes (hub down, S3 down), deployment-level smoke against dev. Those are separate decisions not covered here.
- Browser-timer fast-forward (`page.clock`): not used. The suite accepts the poll-interval floor (see Speed mechanics).

## Approach

Playwright tests run against the existing demo harness (`dashboard/api/_demo/`): the real React UI against the real Flask dashboard API, with K8s/MDRun/Tuner/MDRepo/S3 mocked behind it. The demo is the project's maintained dev loop and its mocks are already test-pinned, which minimizes double-drift.

## Package layout and root wiring

New top-level pnpm workspace member, package name `@mddash/e2e`, private, no published artifacts:

```
e2e/
  package.json            # scripts: test → "playwright test", type-check → "tsc --noEmit", knip → "knip"
  playwright.config.ts
  tsconfig.json           # strict, extends nothing project-external; types via @playwright/test
  knip.json               # entry: tests/**/*.spec.ts
  tests/*.spec.ts
  fixtures/mdposit-cache/ # committed MDPosit payload cache (see Hermeticity)
```

Root wiring (the only files outside `e2e/` and `dashboard/api/_demo/` that change):

- `pnpm-workspace.yaml`: add `e2e` to `packages`.
- Root `package.json`: add `--filter @mddash/e2e` to the existing `knip` and `type-check` parallel scripts; add `e2e` to the oxlint path list; add `e2e/**/*.ts` to the prettier `format`/`format:check` globs.
- Root `.gitignore`: add `e2e/test-results/` and `e2e/playwright-report/`.
- `.github/dependabot.yml`: unchanged — the single root npm entry (`directory: /`, weekly, grouped) already covers all workspace members via the root lockfile, so `@playwright/test` updates flow automatically.
- `.devcontainer/post-create.sh`: add `pnpm --filter @mddash/e2e exec playwright install --with-deps chromium` so local `make e2e` works out of the box.
- `Makefile`: new `.PHONY: e2e` target next to the test targets — `pnpm --filter @mddash/e2e test`. It is part of the documented feedback loop in AGENTS.md but deliberately not part of `make test` (browser install is heavy).
- `@playwright/test` is a devDependency of `@mddash/e2e`, pinned to an exact version (browsers and library must match; Dependabot keeps both in step via `playwright install`).

## Orchestration

`playwright.config.ts` starts both processes via `webServer` and always spawns its own (`reuseExistingServer: false`):

1. API: `uv run --directory dashboard/api python _demo/app.py` with env `PORT=8888`, `MDDASH_DEMO_E2E=1`, `MDDASH_DEMO_ANALYSIS_CACHE=<repo>/e2e/fixtures/mdposit-cache`. Readiness: `GET http://localhost:8888/dash/api/health` (existing unauthenticated endpoint). Boot timeout 180s (first-run `uv sync` may be slow).
2. UI: `pnpm --filter dash dev`. Readiness: `http://localhost:5173/dash/`. The vite dev server already serves the dev runtime-config stand-in at `/dash/runtime-config.json` and proxies `/dash/api` → `http://localhost:8888`.

Ports are fixed: vite runs with `strictPort: true` and its proxy target is hardcoded to 8888, so offsetting ports is not possible. If either port is occupied (e.g. `make demo` is running), Playwright's built-in port-in-use error fails the run before any test executes; the suite never kills foreign processes. In CI the ports are always free.

`baseURL` is `http://localhost:5173/dash/` and specs navigate with paths relative to it (e.g. `goto("experiments/bbbbb")`). A leading slash (`goto("/experiments/...")`) resolves against the host root and escapes `/dash`; the app then boots without its base, the runtime-config fetch hits the vite SPA fallback, and every assertion fails with a dashboard configuration error. This was an observed failure mode during implementation, not a hypothetical.

Playwright constants: `workers: 3`, `fullyParallel: true`, `retries: 0` (interference must surface as failure, never be masked), `expect.timeout: 15_000` (the largest poll interval the inventory exercises is 5s; 15s gives a 3-cycle margin — specs that touch longer-poll flows, e.g. notebook steady polling at 30s, must set a larger per-assertion timeout), per-test `timeout: 90_000`, `webServer` timeout 180s, reporter `list` + `html` (`open: "never"`), `trace: "retain-on-failure"`, `screenshot: "only-on-failure"` (no video — the trace covers the failure timeline without re-encoding).

## E2E mode in the demo harness

One env var, `MDDASH_DEMO_E2E=1`, read once in `_demo/state.py` (`E2E: bool`) and consulted by the mock, seed, and analysis modules. When unset, seeded content and behavior are byte-identical to today. When set: the three E2E-only seeds (`hhhhh` publish journey, `jjjjj` handoff journey, `iiiii` AMBER manual-run journey) are added alongside the standard demo data, and four changes apply:

**Process behavior:** `_demo/app.py`'s `__main__` calls `app.run(debug=False, ...)`. This disables the Werkzeug file-watch reloader, which would otherwise wipe and reseed demo state mid-suite whenever a repo file changes (the reloader restarts re-run `seed_data()`).

**MDPosit access — cache-only:** in e2e mode `fetch_analysis_payload` (analysis_data.py) never performs HTTP. A cache hit returns the committed fixture payload; a miss returns `None` — the same value a real 404 produces, so the affected analysis ends ERROR. This makes hermeticity enforced rather than aspirational: a missing success fixture fails loudly (seed-time materialization or job completion surfaces ERROR), the committed cache directory is never written to by an e2e run, and the pockets negative spec ends ERROR deterministically with no fixture and no dependence on live upstream state.

**Notebooks-repo clone — stubbed:** experiment creation shallow-clones the notebooks repo over the network (`utils.download_git_repo*`, bound into `models.experiment`). E2E mode replaces both functions with offline stubs that create the empty target directory (`_demo/mocks/git.py`, same module-mutation pattern as the k8s mocks). No specced journey reads the cloned content. Demo mode keeps real clones.

**Timing behavior:** every row has a consumer in the spec inventory (noted in brackets); e2e variants that no specced journey consumes do not exist.

| Flow | Demo mode today | E2E mode |
|---|---|---|
| Submitted MDRun GMX/AMBER job (`DEFAULT_GMX_DURATION_SEC = 30.0`, elapsed-time machine in http.py) — consumers: extend/run-submission specs | Transitions by wall clock | Stage schedule per job: stage 0 Preparing (0%) → stage 1 RUNNING (progress + appended log) → stage 2 FINISHED with a real `Performance:` line. A status read only advances a stage, and at most one stage per 1.5s — post-submit invalidation bursts fire several reads per second, so a pure read count collapses all stages instantly (observed in the first parallel run; this floor prevents it while keeping total time-to-FINISHED ~3s). Per-job state (`e2e_stage`/`e2e_stage_at`), independent per submitted job. |
| MDRepo upload job completion (`UPLOAD_JOB_DURATION_SEC = 4.0`, thread sleep in k8s.py) — consumer: spec #5 | 4.0s | 0.5s |
| Submitted analysis completion (`ANALYSIS_JOB_DURATION_SEC = 3.0`, thread delay in k8s.py) — consumer: spec #6 | 3.0s | 0.5s |

Unchanged in e2e mode, because no inventory spec consumes them: tuner trial advancement (10s elapsed machine, seeded and submitted alike), archive/restore/purge completion (4s), all seeded RUNNING jobs (logs keep appending per poll), the seeded RUNNING analysis (25s completion), and stop (synchronous STOPPED).

Rationale for the two mechanisms:

- **Poll-count schedules** replace elapsed-time machines: compressing a wall-clock duration risks skipping intermediate states between two UI polls. Advancing the mock only on status reads makes skipping impossible by construction and works at any client poll interval — the same principle the demo already uses for rolling tuner trials (by `seq`) and per-poll log appends.
- **Hardcoded short threads** for one-shot completions: these flows render their "in progress" UI from client mutation state immediately on submit, so transitional rendering does not hinge on timing; the sleep's only job is to keep completion behind the immediate post-mutation refetch in the common case (~50–300ms of round-trip plus CI jitter), so the active status doc is observable server-side exactly once before the next interval poll sees the terminal state. 0.5s covers that with margin while staying far below every UI poll interval (3–5s). The dominant wait in the suite is the poll cadence the UI uses to notice terminal states, which is production code and untouched — the mock delays contribute ~1s total.

UI poll intervals (3–5s, `*_POLL_MS` constants in the UI) are production code and are not touched. Suite time floor = observed transitions × poll interval; a spec asserting three transitions costs ~15–20s. Suite-wide this lands in the 2–4 minute range.

Specs ban `waitForTimeout`. All waiting is via auto-waiting Playwright assertions (`expect(locator).toHaveText(...)`, `toBeVisible()`, etc.).

## Isolation and determinism

The suite runs 3 Playwright workers in full parallelism against one shared demo instance (one API + one vite server; startup amortized). Parallel safety comes from a disjointness contract, not from locking:

- **Selector discipline**: locate entities by exact seeded name or self-created id — never by list position or count (list pages show every experiment, including ones other specs just created).
- **Dedicated state per mutating spec**, assigned once and not shared: live-run/analysis-run-gmx/locked-simulation read enzyme (`md` sim); extend-run owns enzyme `npt_equilibration`; stop-run and analysis-error share villin (compatible: stopping leaves files, a STOPPED run implies the analysis step); tune-guided owns membrane `aaaaa`; manual-run-amber owns new seed `iiiii` (valid AMBER sim, no jobs); mdposit-handoff owns new seed `jjjjj` (finished GMX run, nothing live — publish marker gating is per selected simulation); publish owns `hhhhh`; notebook mutates notebook status of `eeeee`/`ddddd` (no spec asserts notebook state there); dashboard-chrome renames+deletes disposable `fffff`; create/setup-manual specs create their own experiments. Specs sharing a page use disjoint surfaces or are proven compatible. Shared helpers exist only where ≥2 specs need them (`tests/helpers.ts`).
- **Browser contexts are isolated** per test (cookies/storage separate; each publish spec performs its own demo-MDRepo auth).
- State reset happens once per suite run: the demo wipes and reseeds `MDDASH_DEMO_DATA_DIR` on API start. Specs do not reset mid-run — they are correct under any interleaving by contract.
- **Known hazards and their wind-back levers** (apply only if empirically hit): SQLite `database is locked` under parallel writes → enable `busy_timeout` in the demo profile, else `workers: 2`; seeded-entity interference → re-assign ownership; CPU contention on the CI runner → `workers: 2`. Instance sharding (one API + one vite per worker, own port + `MDDASH_DEMO_DATA_DIR`) remains the known endgame if the suite ever outgrows these levers.

## Hermeticity

The demo intentionally fetches MDPosit analysis payloads over live network in demo mode, cached in `MDDASH_DEMO_ANALYSIS_CACHE` (default `~/.cache/mddash-demo/`). In e2e mode the network path is disabled entirely (see E2E mode: MDPosit access — cache-only), so hermeticity is enforced by the harness. The committed fixture `e2e/fixtures/mdposit-cache/MD-A003ZT.2/*.json` must contain exactly the payloads the suite consumes: every analysis materialized at seed time plus the payload for the seeded RUNNING analysis when it completes mid-run. A missing payload ends the corresponding analysis ERROR — loud where the suite asserted success. The pockets negative spec needs no fixture: a cache miss is precisely the ERROR it asserts. Refresh procedure (upstream payload drift): set `MDDASH_DEMO_ANALYSIS_CACHE` to the fixture dir, run `make demo` (demo mode keeps network access), let seeding and one analysis completion repopulate the payloads, commit the result.

## Spec inventory

Journeys are derived from the user guides in `docs/guides/` (guide file in brackets). Both engines are covered for every job-bearing flow.

| Spec | Journey | Guide | Engine |
|---|---|---|---|
| live-run | dashboard → live run view with streaming logs | 02, 06 | GMX |
| create-experiment | new experiment from PDB id → Setup | 01 | GMX |
| setup-manual-gmx | Upload Files source → manual manifest form, auto-fill, step unlock | 01, 04 | GMX |
| setup-manual-amber | same, AMBER engine toggle + AMBER roles | 01, 04 | AMBER |
| tune-guided | tuner running view, trials table, failed-trial logs, stop tuning, pick trial → Run Simulation → Finished | 05, 06 | GMX |
| manual-run-amber | manual configuration (Binary/Ewald) → Run Simulation → Finished | 05, 06 | AMBER |
| stop-run | stop a running job → Stopped; assert no Extend on AMBER (engine asymmetry) | 06 | AMBER |
| extend-run | extend stopped run → Finished, then Re-run destructive reset → one fresh segment | 06 | GMX |
| analysis-run-gmx | successful RMSD analysis submission to completion | 07 | GMX |
| amber-analyze | ready analysis results + trajectory viewer mounts | 07 | AMBER |
| analysis-error | pockets → ERROR; durable alert "Previous analysis run failed." | 07 | AMBER |
| publish | MDRepo auth bypass → upload → draft → "Finish in MDRepo" | 08 | GMX |
| mdposit-handoff | MDPosit target → prepare → four download links | 08 | GMX |
| published-view | Published card, record link, disabled "Publish a new version" | 08 | GMX |
| notebook | limit dialog (both seeded notebooks running) → stop → start → status bar → stop | 02, 09 | (eeeee) |
| dashboard-chrome | search filter, rename, delete (disposable fffff) | 02 | — |
| locked-simulation | Locked badge + disabled form on a job-referenced simulation | 04 | GMX |

Knowingly not covered: JupyterLab internals (`setup.ipynb`/`analysis.ipynb` are external apps), start-tuning confirm dialog and re-tune destruction (covered paths reach the same endpoints), stop-calculation (0.5s completion cannot be reliably caught mid-flight), preprocessing Image/Fit choices, membrane analyses, trial Fastest/Eco badge ranking, quota-exceeded toast, hub-level flows (server start/stop, tokens).

## Workflow

New file `.github/workflows/e2e.yml`; `workflow_dispatch` is the only trigger — E2E runs on demand, never in PR CI, never called by `cd.yml`/`release.yml`.

- `permissions: contents: read`; `concurrency: ${{ github.workflow }}-${{ github.ref }}` with `cancel-in-progress: true`; `timeout-minutes: 15`.
- Steps: `actions/checkout` (pinned SHA, `persist-credentials: false`) → `./.github/actions/setup-frontend` → `astral-sh/setup-uv` (cache enabled, keyed on `uv.lock`) → `pnpm --filter @mddash/e2e exec playwright install --with-deps chromium` → `make e2e`.
- On failure: `actions/upload-artifact` (pinned SHA, `if: failure()`) with paths `e2e/playwright-report/` and `e2e/test-results/`.
- `make lint-workflows` (actionlint + zizmor, `--min-severity high`) covers the new workflow; per repo convention, secrets/templates are passed via `env:` blocks only (none needed here).

## Relationship to the Vitest layer

E2E does not replace unit/component tests. Every surviving test must answer: *"name the realistic accident this catches, or the non-obvious behavior it pins."*

- **Kept**: pure-logic tests (parse/format/log-text/errors/runtime-config/live-work, etc.) and component state machines with combinatorial edges (run/analyze/tune steps, publish, forms, notebooks).
- **Pruned**: 12 journey/UI-assembly files deleted (~3k of ~6k lines; 38 → 26 files, 319 → 203 tests): wizard, dashboard, experiment-card, app-shell, site-header, server-status-bar, stepper, step-guide, module-icon, source-metadata, new-experiment-page, notebook-quota-dialog. Nothing was moved or refactored in production code to keep any pin.
- Rule going forward: verify at the lowest layer that can express the assertion — pure decision → unit; client interaction matrix → component; needs real API + browser → E2E.

## Risks and mitigations

- **Demo mock drift from real integrations** — mitigated: the demo is the primary dev loop, mocks are test-pinned, and `_demo/AGENTS.md` documents the invariants.
- **Timing flake around the 0.5s thread delays** — mitigated: auto-waiting assertions with a 15s expect timeout; delays sized as a margin over immediate-refetch latency, with terminal states always asserted via auto-wait rather than timing assumptions; traces retained on failure.
- **MDPosit fixture staleness** — mitigated: single pinned project with documented refresh; e2e mode disables the network path, so a stale or missing fixture fails loudly as an ERROR instead of silently passing via live fetch.
- **State wipe mid-run from the Werkzeug reloader** — eliminated by `debug=False` in e2e mode.
- **Parallel interference** — mitigated by the disjointness contract and the entity-assignment table; empirically-hit limits wind back via documented levers (`busy_timeout` in the demo profile, fewer workers, instance sharding).

## Verification

- `make fix`, `make type-check`, `make knip`, `make test` all green (existing loop extended to the new package).
- `make e2e` green locally and via a manual workflow dispatch; the workflow lints clean under `make lint-workflows`.
- `make demo` behavior unchanged with `MDDASH_DEMO_E2E` unset (manual spot check of upload/run timings).
- Determinism: 3 consecutive manual workflow runs at `workers: 3` without flake.
