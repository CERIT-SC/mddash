# ADR 0001: Offload simulation jobs to HPC via interLink, keep the mdrun-api head local

- **Status**: Accepted
- **Date**: 2026-10-20

## Context

We want to run molecular dynamics payload jobs (GROMACS/AMBER) on HPC clusters reached through [interLink](https://github.com/interlink-hp), which exposes HPC batch systems (SLURM) to Kubernetes as virtual nodes. interLink does not bridge PersistentVolumeClaims to the remote side, so any pod scheduled on a virtual node must not depend on cluster storage. Two architectures were considered:

- **A. Head local.** The mdrun-api Deployment (Flask API + poller sidecar + SQLite on its block PVC) stays on regular cluster nodes; only the payload Job pods it creates target the virtual node.
- **B. All remote.** The whole mdrun-api service runs on/behind the remote cluster.

Payload Job pods were already redesigned to be PVC-free (see `mdrun-api/k8s_client.py`): a shared `emptyDir` plus three containers that stage data through S3 (`s3-init` pull, simulation, `s3-sync` push). The mdrun-api server itself never reads or writes simulation data — it exchanges only job IDs, statuses, and bucket-relative filenames.

## Decision

Architecture **A**. Payload Jobs target the interLink virtual node through two optional environment variables on the mdrun-api Deployment — `JOB_NODE_SELECTOR` and `JOB_TOLERATIONS` (JSON) — injected from `mdrunApi.jobScheduling` in `config*.yaml`. Unset (the default), the Job manifest is identical to a plain single-cluster deployment, which is enforced by a unit test. Offload is all-or-nothing per deployment.

**Option B is rejected** because:

1. The head's SQLite database requires WAL mode, which is unsupported on network filesystems — it needs a block-device-backed PVC that the remote side cannot attach. Losing that guarantee means swapping the database or accepting corruption.
2. The Deployment is pinned by the RWO PVC (`strategy: Recreate`, single replica). Moving it remote buys no scaling, only a new storage problem.
3. The poller sidecar continuously talks to the Kubernetes API server; the head never touches simulation data, so there is no data-locality benefit to offset the above.
4. Callers (dashboard API in every user pod) reach the head at a stable in-cluster Service address with unchanged latency.

## Consequences

- Requirements on the interLink side: `emptyDir` and multi-container pods supported; HPC nodes can reach `S3_ENDPOINT` (egress) and pull the GMX/AMBER and rclone images; the virtual node advertises GPU resources under the configured `GPU_TYPE` name; SLURM walltime is set as a node-level default; partition is chosen per virtual node.
- Job status, stop, and delete still flow through the ordinary Kubernetes Job/pod APIs; the virtual kubelet must round-trip Job completion (`Complete`/`Failed`) and propagate Job deletion to `scancel`. Both are verified by the canary procedure in `docs/deployment.md` before enabling offload in an environment.
- A future move to selective routing (some jobs local, some remote) would add a per-job field to the create API; the all-or-nothing env knobs remain the fallback.
