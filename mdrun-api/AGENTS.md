# MDRun API

## Mission

Manage GROMACS and AMBER molecular dynamics simulation jobs on Kubernetes with automated status tracking and S3 data synchronization. Runs in the admin namespace.

## Why These Patterns

- `MdrunJob` couples DB records with K8s resources; the poller sidecar (`python -m polling` with `POLL_INTERVAL_SECONDS`) runs in the same pod, sharing the `/data` PVC. Co-locating writer and volume on one node lets SQLite live on a block-device-backed filesystem instead of NFS — WAL is unsupported on network filesystems and causes `disk I/O error`. Polling avoids webhook complexity without tying scheduling to the web process.
- GMX and AMBER routes share `_get_job`/`_delete_job` helpers. `MdrunJob.status` queries K8s on every access.

## Critical Gotchas

- **SQLite WAL needs a block-device-backed filesystem**: the `/data` PVC MUST use a block storage class (currently `csi-ceph-rbd-du`, set in `config.yaml`), never NFS — or commits fail with `sqlite3.OperationalError: disk I/O error`. `storageClassName` is immutable on an existing PVC, so switching classes requires deleting and recreating it.
- **On-demand status**: `MdrunJob.status` queries Kubernetes on every access — cache results if polling frequently.
- **Delete ordering**: delete K8s resources before committing the DB deletion. If K8s cleanup fails, the DB record stays so the job can be retried/cleaned later. TERMINATED/ERROR jobs are auto-deleted from K8s but preserved in DB.
- **Input sanitization**: all user inputs MUST pass through `sanitization.py` to prevent shell injection in K8s job manifests.
- **Case-insensitive enums**: `from_string` on all enums (`DeviceType`, `AmberBinary`, `EwaldPreset`, `JobStatus`) is case-insensitive — `PMEMD.CUDA` and `pmemd.cuda` are equivalent.
- **S3 + GPU**: `S3_ENDPOINT`/`S3_ACCESS_KEY`/`S3_SECRET_KEY` must be set or the API logs errors on startup. GPU resource type comes from `GPU_TYPE` (set via `gpuType` in config.yaml); defaults to empty if unset.
- **K8s jobs** are named `mdrun-{uuid}` — never manually create jobs with this prefix.
- **Health logs**: successful `/api/health` probe access logs are suppressed (Gunicorn logger class) to avoid log congestion; failed probes, 4xx/5xx, startup logs, and app errors stay visible.
- **Problem-details errors**: routes raise `HTTPException` or `ValidationError`; global `@app.errorhandler` handlers in `errors.py` convert to RFC 9457 `{"type": "urn:mddash:<token>", "title": "...", "detail": "...", ["solution": "..."]}` responses. The `type` token is the support-reportable code. No `@handle_exceptions` decorator. Rollback is automatic. Validation uses `schema.load()` — `np`/`ntomp` use `Range(gt=0)`, enums convert via `@post_load`.
