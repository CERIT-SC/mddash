# Remove GMX Sidecar — Design Spec

**Date:** 2026-04-26
**Status:** Approved

## Problem

Notebook pods currently run two containers: `jupyter` and `gmx` (sidecar). The gmx sidecar runs `sleep infinity` and receives GROMACS commands via `kubectl exec` through a proxy script in the notebook image.

Issues with the current approach:

- **Engine-specific dead end.** AMBER support (ready to merge) has no sidecar. biobb_amber shells out to `tleap`, `antechamber`, `sander`, `cpptraj`, `pdb4amber`, `reduce` — six-plus binaries, each would need a separate proxy script. The sidecar pattern does not scale to multiple engines.
- **Resource waste.** Binder repos using biobb install their own GROMACS via conda (binder env PATH prepended before image PATH), making the gmx sidecar idle while still consuming CPU/memory quota.
- **kubectl exec overhead.** Every `gmx` call in a notebook crosses a container boundary via kubectl exec.
- **Complexity without proportional benefit.** GPU for gmx EM is the sidecar's only surviving justification. This is achievable by attaching the GPU to the jupyter container directly.

## Decision

Remove the gmx sidecar. Bundle GROMACS and AmberTools binaries directly in the notebook image via multi-stage Dockerfile. Attach GPU to the jupyter container when requested.

## Architecture

### Notebook Image (multi-stage Dockerfile)

```
Stage 1: cerit.io/ljocha/gromacs:2026-1-plumed-2-10-afed-pytorch-model-cv-2_ray-2-54-0_1
Stage 2: cerit.io/xkrasa/amber:24
Final:   quay.io/jupyter/base-notebook:latest
```

From the GROMACS stage:
- Copy `gmx` binary
- Copy all non-CUDA shared library dependencies (enumerated via `ldd` at build time)
- CUDA driver libs come from NVIDIA Container Runtime at pod startup — not bundled

From the AMBER stage:
- Copy AmberTools binaries: `tleap`, `antechamber`, `sander`, `cpptraj`, `pdb4amber`, `reduce`
- Copy `$AMBERHOME/dat/` (force field parameters and residue templates — required by tleap at runtime)
- Copy shared library dependencies

CUDA libraries (libcudart, libcublas, etc.) are NOT copied. The NVIDIA Container Runtime auto-mounts them from the host into any container requesting `nvidia.com/gpu`. This is documented NVIDIA Container Toolkit behavior, not an assumption.

Non-CUDA library dependencies (PLUMED, PyTorch, Ray for GROMACS; AmberTools deps) must be explicitly copied. Exact paths determined during implementation by inspecting source images with `ldd` and `docker run`.

### Environment Variables in Final Image

```dockerfile
ENV AMBERHOME=/opt/amber
ENV PATH="/opt/amber/bin:${PATH}"
ENV LD_LIBRARY_PATH="/opt/amber/lib:${LD_LIBRARY_PATH:-}"
```

GROMACS libraries registered via `/etc/ld.so.conf.d/gromacs.conf` + `ldconfig`.

### Binder Env Compatibility

No change. `setup-binder-env` still prepends binder env to PATH. Biobb repos that install their own GROMACS or AmberTools via conda take priority — correct behavior. Repos without MD tools fall back to image-installed binaries.

## Pod Changes

### Container count: 2 → 1

`create_notebook_pod` in `dashboard/api/clients/k8s.py` drops the gmx container spec. Pod spec has a single `jupyter` container.

### GPU attachment

`gpu=True` adds `nvidia.com/gpu: 1` to `notebook_resources` (jupyter container) instead of `gmx_resources` (former sidecar). Semantics of `Notebook.gpu` DB column unchanged — boolean still means "attach GPU to this notebook." No migration needed.

### Resource model

| Before | After |
|--------|-------|
| `NOTEBOOK_RESOURCES` + `GMX_RESOURCES` | `NOTEBOOK_RESOURCES` only |
| Tier scaling multiplies two dicts | Tier scaling on one dict |
| Quota: sum both containers | Quota: single container |
| `get_tier_resources()` returns `(nb_res, gmx_res)` tuple | Returns single `nb_res` dict |

## Code Changes

### `notebook/Dockerfile`
- Add multi-stage build with GROMACS and AMBER stages
- Copy binaries and deps as described above
- Remove the existing `gmx` proxy script (no longer needed — binary is local)

### `dashboard/api/clients/k8s.py` — `create_notebook_pod`
- Remove `gmx_resources` parameter
- Remove `effective_gmx` construction and GPU injection into gmx resources
- Remove `gmx_container` construction
- GPU injected into `notebook_resources` when `gpu=True`
- Pod spec `containers` list: `[jupyter_container]` only

### `dashboard/api/models/notebook.py`
- `get_tier_resources()`: return single `nb_res` dict instead of `(nb_res, gmx_res)` tuple
- `Notebook.start()`: remove `gmx_res` usage, pass single resource dict to `create_notebook_pod`
- Quota calculation: remove gmx resource summation (L130-133)
- Remove `gmx_resources` parameter from `create_notebook_pod` call

### `dashboard/api/config.py`
- Remove `GMX_IMAGE`
- Remove `GMX_RESOURCES` dict and env var reads (`GMX_CPU_REQUEST`, `GMX_CPU_LIMIT`, `GMX_MEMORY_REQUEST`, `GMX_MEMORY_LIMIT`)
- Update validation check (no longer includes `GMX_RESOURCES`)

### `scripts/resource_summary.py`
- Remove gmx resource lines (L176-179: `gmx_cpu_req`, `gmx_mem_req`, `gmx_cpu_lim`, `gmx_mem_lim`)
- Update quota calculation to use notebook resources only

### `helm/charts/mddash/values.yaml.tmpl`
- Remove `gmxCpuRequest`, `gmxCpuLimit`, `gmxMemoryRequest`, `gmxMemoryLimit` from `resources.notebook`
- Remove `GMX_IMAGE` from API container env

### `config.yaml` + `config.dev.yaml` + `config.edc.yaml`
- Remove `gmxImage` top-level field
- Remove `gmxCpuRequest`, `gmxMemoryRequest`, `gmxCpuLimit`, `gmxMemoryLimit` under `resources.notebook`

### `helm/charts/mddash/files/pre_spawn_hook.py`
- Remove `GMX_IMAGE`, `GMX_CPU_REQUEST`, `GMX_MEMORY_REQUEST`, `GMX_CPU_LIMIT`, `GMX_MEMORY_LIMIT` from `_API_PASSTHROUGH_ENV` list

### `notebook/run-notebook.sh`
- Update comment: remove reference to "gmx sidecar"

### `dashboard/api/_demo/mocks/k8s.py`
- Update `create_notebook_pod` mock to drop `gmx_resources` parameter and gmx container references

## What Does NOT Change

- `Notebook.gpu` DB column and migration: semantics preserved, no schema change
- `GPU_TYPE` env var in config: still controls which GPU resource type to request
- MDRun API: AMBER and GROMACS production jobs unaffected — they already run as separate K8s Jobs
- Binder env setup scripts: no change
- Caddy proxy, auth service, JupyterHub config: no change
- `run-notebook.sh` pod self-deletion logic: no change

## Open Items for Implementation

1. Inspect GROMACS image: `docker run --rm cerit.io/ljocha/gromacs:... ldd $(which gmx)` — enumerate all non-CUDA `.so` deps and their paths
2. Inspect AMBER image: `docker run --rm cerit.io/xkrasa/amber:24 find /opt/amber -type d` — locate bin, dat, lib directories
3. Verify `tleap` works with copied `$AMBERHOME/dat/` by running a minimal tleap command in the built image
4. Verify `gmx mdrun` GPU acceleration works in built image with NVIDIA runtime (test on GPU node)
