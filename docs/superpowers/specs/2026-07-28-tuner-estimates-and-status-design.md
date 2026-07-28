# Tuner Estimated Time/Cost Metrics + FINISHED Status

**Date:** 2026-07-28
**Status:** Approved

## Goal

1. Enrich tuning trial responses with `estimated_time` (hours) and `estimated_cost` fields,
   computed from measured performance and the *full production* simulation length (not the
   tuner's `-nsteps` benchmark override), displayed as new columns in the TunerTable UIs.
2. Rename the tuner status `TERMINATED` (meaning "finished successfully") to `FINISHED`,
   and re-color UI badges: finished → green (`success`), running → yellow (`warning`, same
   as pending).

## Scope

- Tuner API (FastAPI + Ray), both GMX and AMBER engines.
- Dashboard API: enum forward-compatibility + demo mocks (trials/trials payload pass
  through unchanged otherwise).
- Dashboard UI: `TunerJobStatus` type, `TunerTable`, `AmberTunerTable`, polling hook.
- **Out of scope:** MDRun job statuses (separate service, legitimately uses `TERMINATED`).

## Design

### Estimated time

- Sim length `sim_length_ns` is extracted once per job at submission and stored in a new
  nullable `sim_length_ns` column on the tuner `Job` model (Alembic migration `002`).
- **GMX:** a small `@ray.remote` task on a worker runs `gmx dump -s <tpr>` (workers have
  GROMACS; the API pod does not) and regex-parses `nsteps` and `delta-t`.
  `sim_length_ns = nsteps * delta_t / 1000`. Failure → None.
- **AMBER:** parses `nstlim` and `dt` from the uploaded original mdin (plain text,
  in-process). `sim_length_ns = nstlim * dt / 1000`.
- `estimated_hours = sim_length_ns / performance * 24` — null when performance or
  sim_length_ns is missing.

### Estimated cost

- New `tuner/api/pricing.py`; rates from env with industry-typical defaults:
  `COST_CPU_CORE_HOUR=0.04`, `COST_GPU_HOUR=3.00`, `COST_GB_RAM_HOUR=0.005`.
- Resource model mirrors MDRun `k8s_client.py`:
  - GMX: cores = `np×ntomp`, gpus = 1 if nb or pme is gpu, RAM = `4×np` GB.
  - AMBER: pmemd.MPI → cores = `np×ntomp`, RAM = `4×np` GB, 0 GPUs; pmemd.cuda →
    cores = `ntomp`, RAM = 4 GB, 1 GPU.
- `estimated_cost = estimated_hours × (cores×cpu_rate + gpus×gpu_rate + ram×ram_rate)`.
- Estimates computed at response-serialization time in the routers (always reflect current
  rates; nothing per-trial persisted).

### Status rename

- Tuner `JobStatus.TERMINATED` → `FINISHED` everywhere (rayworker, routers, tests).
- Migration `002` also rewrites stored `TERMINATED` values in `jobs`/`trials`.
- Dashboard `enums.JobStatus` gains `FINISHED` (keeps `TERMINATED` for MDRun jobs).
- UI gets a separate `TunerJobStatus` type (`FINISHED` instead of `TERMINATED`) and
  `getTunerJobStatusVariant()`: FINISHED→success, RUNNING→warning, PENDING→warning,
  ERROR→destructive, UNKNOWN→secondary. Production job tables untouched.
- Unknown/legacy badge values render defensively (secondary/rank-last).

### UI

- `TunerTable` + `AmberTunerTable`: new right-aligned **Est. Time** and **Est. Cost**
  columns after Performance; "—" when null; tooltips explaining the estimate basis.
  Time formatted as `42 min` / `12.5 h` / `2.3 d`; cost as `$1.84` (`<$0.01` when tiny).
- `useTunerStatus` polling stops on `FINISHED` as well as `ERROR`/stopped.
- Demo mocks updated (FINISHED statuses + estimated fields).

## Testing

- Tuner: unit tests for pricing math, resource model, tpr dump parsing, mdin nstlim/dt
  parsing; updated router/orchestration tests for FINISHED and new fields.
- `make fix`, `make type-check`, `make test` from repo root must pass.
