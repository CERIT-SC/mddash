# Tuner

## Mission

Benchmark GROMACS and AMBER execution configurations through a FastAPI service backed by Ray workers. Tuner runs in the admin namespace and is consumed by the dashboard API.

## Runtime Invariants

- SQLite uses WAL mode at `/data/tuner.db`. The `tuner-db` PVC must be RWO block storage, never NFS.
- Uploaded inputs, trial outputs, and logs live under `/tmp/tpr` on the RWX `tuner-jobs` PVC shared with Ray head and worker pods.
- The API deployment uses `Recreate` because its database PVC cannot be attached to two pods.
- Alembic migrations run before API startup. Migration failure must stop startup.
- KubeRay and its CRDs are cluster prerequisites; the MDDash chart does not manage the operator.
- Ray head and workers are ingress-isolated by NetworkPolicy; only Tuner pods may connect directly to them.
- Tuner credentials are required at startup. Never restore development credential defaults.

## Worker Image

- `tuner-worker` is large and includes licensed AMBER artifacts.
- Build and push it manually through `tuner/worker/Makefile` using a static stack tag.
- Never add the worker to root aggregate build/push targets or GitHub Actions.
- The chart must consume the complete worker image reference from `config*.yaml` without applying the MDDash release tag.

## Restart Semantics

Active threads, cancellation events, and Ray object references are process-local. API restarts can leave remote work orphaned and mark persisted active jobs as failed. Do not claim restart-safe active jobs without a separate durable reconciliation design.

The current Basic Auth credential is shared by dashboard API sidecars and does not encode job ownership. Keep the API cluster-internal and treat per-user authorization as a separate required security design.
