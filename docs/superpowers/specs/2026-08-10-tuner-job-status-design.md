# Tuner Job Status: Ray-Ground-Truth Trials and Start Watchdog

Date: 2026-08-10
Component: `tuner/` (tuner-api only; no chart changes; no dashboard/UI changes)

## Background

This spec resulted from a tuner quality review. Findings, and the decisions taken:

### How we know a tuning job has finished

The trial universe is the full generated grid (`engine.generate_configs()`), created as PENDING rows up front, ordered by priority. The job thread walks the list (baseline of 3, then batches of 6) and writes `FINISHED` only when the grid is exhausted. This definition stands unchanged: **FINISHED = every trial reached a terminal state**.

### Schedulability of trials

Configs exceeding `MAX_CPU`/`MAX_GPU` are filtered out at generation, and the chart wires both from the same values as the Ray worker template (`ray.worker.numCpu`/`numGpu`: 32 CPU, 1 GPU per worker, autoscaling 0–5 workers). So every generated config fits a single worker pod by construction, and the KubeRay autoscaler provisions workers on demand. There is no per-trial "unrunnable" class: either the cluster provides workers and every trial eventually runs, or it provides none and nothing runs.

Ray does **not** offer a per-task verdict for "cannot be scheduled": the State API reports `PENDING_NODE_ASSIGNMENT` for both "waiting for autoscaling" and "stuck forever". The only user-visible hang is a job stuck in RUNNING for hours with zero progress because `ray.wait` blocks indefinitely.

### Trial status today is a guess

`_submit_trials` writes `RUNNING` the moment a task is *submitted* to Ray, so a trial shows RUNNING while it is actually queued (`PENDING_NODE_ASSIGNMENT`). This spec derives trial and job status from Ray task ground truth instead — the states "as Ray intended": `PENDING_*` → PENDING, `RUNNING*` → RUNNING, terminal states owned by the job thread.

## Goals

- Report honest statuses: a trial shows PENDING wherever it is not executing in Ray (unsubmitted *or* queued); RUNNING only while Ray reports the task executing.
- Derive the job status from effective trial statuses: PENDING until the first trial executes, RUNNING monotonically after, FINISHED at grid exhaustion, terminal DB states (ERROR stalls/cancels) always win.
- Bound the two non-terminating paths: cold-start / starvation (nothing ever begins) and mid-run starvation (trials stop beginning) with one watchdog rule.

## Non-Goals

- No new statuses: no QUEUED enum anywhere (tuner, dashboard, UI untouched).
- No changes to grid generation, ordering, batch sizes, or early-stop thresholds. Batches (baseline 3, then 6) are load-bearing for the pruner — trials receive `best_steps_per_sec` at submission time — and must not be flattened into a submit-all or streaming-refill loop.
- No per-trial wedge timer: a wedged RUNNING process that is a batch's last remaining trial is a known, accepted gap (it shows as RUNNING forever). Documented here only.
- No per-user authorization, no restart-safe active jobs (documented invariants in `tuner/AGENTS.md` remain).

## Design

All changes live in `tuner/api/rayworker/tuner.py`, `tuner/api/config.py`, and the two GET-status routers (`routers/gmx.py`, `routers/amber.py`).

### 1. State plumbing

- `JobState.futures` becomes a `future → trial_id` mapping so any code path can map an active Ray task back to its DB trial. `add_futures`/`get_futures`/`remove_future` signatures adjust accordingly. `cancel_job` iterates the map keys — behavior unchanged.
- `_task_states(job_id) -> dict[int, str]`: for each active future, query the Ray State API (`ray.util.state.get_task(str(future.task_id()), address=...)`) and return `trial_id → task state string`. Bound per call by the active batch size (≤ 6). The dashboard address derives from `RAY_ADDRESS` (head service, dashboard port 8265); reachability from the API pod is already permitted by `tuner-ray` NetworkPolicy (any `tuner`-labeled pod → ray pods, all ports). Query failures or unknown tasks yield *absent* entries — never an exception to the caller.
- `trial_status_overrides(job_id) -> dict[int, JobStatus]`: built from `_task_states`; a submitted trial whose Ray state starts with `RUNNING` maps to `JobStatus.RUNNING`. This is the only non-terminal override.

### 2. Submission keeps trials PENDING

`_submit_trials` drops its `update_trial_result(trial_id, JobStatus.RUNNING, None)` call. Trials remain PENDING in the DB until the job thread writes a terminal state on completion. Terminal transitions (FINISHED/ERROR, including early-stopped) are written by `_process_trial_results` exactly as today.

### 3. Read-time rendering (both GET status routers)

Before building the trial list in the response, fetch `trial_status_overrides(job_id)` and apply: for a trial whose DB status is PENDING, use the override when present (RUNNING); otherwise keep the DB status. Trials with non-PENDING DB status are never overridden. No DB writes on the read path.

Effective **job** status in the same response — derived, not stored:

- DB status terminal (FINISHED/ERROR) → report as-is.
- Else, if any effective trial is RUNNING or already terminal → report RUNNING.
- Else → report PENDING.

This makes job PENDING→RUNNING monotonic at first actual execution and keeps all existing DB writes untouched.

### 4. Start watchdog in `_process_trial_results`

One constant, hardcoded in `tuner/api/config.py` next to `EARLY_STOP_*`:

```python
TRIAL_START_TIMEOUT_SECONDS = 7200  # 2h; fail job if no trial begins or completes in this window
```

The wait loop changes from a bare `ray.wait(pending_futures, num_returns=1)` to a ticker-free guarded wait:

```python
done, pending_futures = ray.wait(pending_futures, num_returns=1, timeout=TRIAL_START_TIMEOUT_SECONDS)
if not done:
    states = _task_states(job_id)  # trial_id -> Ray task state, only for pending_futures
    if any state in states.values() starts with RUNNING:
        continue  # a trial is executing; extend the window from here
    # 2h with no completion AND nothing running => nothing began => unschedulable
```

On the unschedulable path:

1. Log job_id and the remaining trial IDs.
2. `ray.cancel(future, force=False)` for each remaining future (same teardown as `cancel_job`).
3. `update_trial_result(trial_id, JobStatus.ERROR, None)` for each remaining trial in the current batch.
4. Raise `RuntimeError("No trial began or completed within 7200s; cluster busy or unavailable — retry later")`; the existing outer `except` writes job `ERROR` with that message. Trials of never-submitted later batches stay PENDING, which reads honestly.

Why this rule is equivalent to "no progress for 2h": a task that *began* either completes (the wait returns it — including failures, which surface as `RayError` on `get`) or is still executing (visible as RUNNING in the state query). The state check at expiry therefore detects "started" without per-tick polling or transition bookkeeping.

Scenarios:

- Cold start, dead worker pool: everything pending, nothing running → fires at 2h. Realistic provisioning (autoscaler scale-up + large worker image pull) is tens of minutes, so no false fire.
- Inter-job contention: another user's grid camping the workers looks identical and triggers the same ERROR — intentional; the message says busy-or-unavailable and the user can retry.
- Slow-but-progressing jobs: any RUNNING trial (or any completion) resets/extends, so they are never killed.

Known accepted gap: a wedged RUNNING process (never advances steps) that becomes a batch's last remaining trial shows RUNNING forever and is not killed by this watchdog.

### 5. Testing

Extend `tuner/tests/rayworker/test_tuner.py` and the router tests:

- Submit keeps trials PENDING (no optimistic RUNNING write).
- `trial_status_overrides` maps Ray RUNNING states to RUNNING; query failures yield no override; PENDING Ray states yield no override.
- GET status renders: queued submitted trial → PENDING; Ray-RUNNING trial → RUNNING; terminal DB states never overridden.
- Derived job status: PENDING before any execution; RUNNING once any effective trial is RUNNING or terminal; terminal DB status wins.
- Watchdog: empty `ray.wait` + all trials pending/queued → trials ERROR, futures `ray.cancel`ed, job ERROR with the stall message. Empty wait + any RUNNING → loop continues (no DB status changes). `_task_states` failure (no states) treated as "nothing running" → stall path.
- Existing tests asserting the optimistic RUNNING write are updated to the PENDING contract.

### 6. Docs

Add one paragraph to `tuner/AGENTS.md` noting that trial/job RUNNING reflect Ray task ground truth at read time, and that jobs stall-fail after 2h without a started trial.

### Verification

From repo root: `make fix`, `make type-check`, `make test`.
