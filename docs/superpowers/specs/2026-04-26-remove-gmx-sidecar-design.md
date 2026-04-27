# Remove GMX Sidecar -- Design Spec

**Date:** 2026-04-26
**Status:** Approved

## Problem

Notebook pods currently run two containers: `jupyter` and `gmx` (sidecar). The gmx sidecar runs `sleep infinity` and receives GROMACS commands via `kubectl exec` through a proxy script in the notebook image.

Issues with the current approach:

- **Engine-specific dead end.** AMBER support (ready to merge) has no sidecar. biobb_amber shells out to `tleap`, `antechamber`, `sander`, `cpptraj`, `pdb4amber`, `reduce` -- six-plus binaries, each would need a separate proxy script. The sidecar pattern does not scale to multiple engines.
- **Resource waste.** Binder repos using biobb install their own GROMACS via conda (binder env PATH prepended before image PATH), making the gmx sidecar idle while still consuming CPU/memory quota.
- **kubectl exec overhead.** Every `gmx` call in a notebook crosses a container boundary via kubectl exec.
- **Complexity without proportional benefit.** GPU for gmx EM is the sidecar's only surviving justification. This is achievable by attaching the GPU to the jupyter container directly.

## Decision

Remove the gmx sidecar. Install GROMACS and AmberTools binaries directly in the notebook image via dedicated conda environments. Copy `pmemd` GPU-accelerated binaries from the existing AMBER image via multi-stage Dockerfile. Attach GPU to the jupyter container when requested.

## Architecture

### Notebook Image (multi-stage Dockerfile)

```
Stage 1: cerit.io/xkrasa/amber:24   (pmemd + AmberTools, compiled from source)
Final:   quay.io/jupyter/base-notebook:latest
```

#### GROMACS (conda-forge)

The upstream GROMACS image (`cerit.io/ljocha/gromacs`) contains a multi-arch build dispatch wrapper that selects the optimal AVX variant at runtime. This binary carries ~4 GB of transitive dependencies via a full conda env (PyTorch, Ray, MKL, PLUMED, MPI). Copying individual `.so` files is impractical -- the dependency graph is too deep and CUDA stubs require runtime replacement.

Instead: install `gromacs=2026` from conda-forge into a dedicated environment:

```dockerfile
ENV CONDA_OVERRIDE_CUDA=12.0
RUN mamba create -n gromacs -c conda-forge -y gromacs=2026 \
    && mamba clean -afy
```

conda-forge ships a CPU+dispatch build that selects the correct AVX variant at runtime. No CUDA libs are bundled (`CONDA_OVERRIDE_CUDA` allows the solver to accept CUDA metadata without having a GPU at build time); the NVIDIA Container Runtime mounts real CUDA libs from the host at pod startup.

#### AMBER (pmemd + AmberTools, multi-stage COPY)

The `amber:24` image is a multi-stage build that compiles both pmemd (with CUDA/MPI) and AmberTools from source. It provides:

- `/opt/ambertools25/bin/` -- `tleap`, `antechamber`, `sander`, `cpptraj`, plus internal tools
- `/opt/pmemd24/bin/` -- `pmemd`, `pmemd.cuda`, `pmemd.MPI`, `pmemd.cuda_DPFP`, `pmemd.cuda_SPFP`, etc.
- `/opt/ambertools25/lib/` -- shared libraries for both AmberTools and pmemd
- `/opt/ambertools25/dat/` -- force field parameters, residue templates (needed by `tleap`)

The build stage is `nvidia/cuda:12.8.1-devel-ubuntu22.04`; the runtime stage is `nvidia/cuda:12.8.1-runtime-ubuntu22.04`. The final stage installs `libgfortran5` (Ubuntu 24's GCC-13 package lacks the runtime) so pmemd links correctly.

Copy both trees into the notebook image:

```dockerfile
COPY --from=amber /opt/ambertools25 /opt/ambertools25
COPY --from=amber /opt/pmemd24      /opt/pmemd24
```

`AMBERHOME` points to the AmberTools tree so `tleap` resolves force field dat:

```dockerfile
ENV AMBERHOME=/opt/ambertools25
```

pmemd links against `libgfortran.so.5` (system lib); `pmemd.cuda` links against CUDA libs (`libcufft`, etc.) that come from the NVIDIA Container Runtime at pod startup.

No `pdb4amber` or `reduce` in the AmberTools source build -- these are convenience scripts not part of the core build. Users who need them can install via binder env (conda-forge has `ambertools` which includes `pdb4amber`, and ` Reduce` via bioconda).

#### PATH ordering and binder compatibility

```dockerfile
ENV PATH="/opt/pmemd24/bin:/opt/ambertools25/bin:/opt/conda/envs/gromacs/bin:${PATH}"
ENV LD_LIBRARY_PATH=/opt/ambertools25/lib:/opt/pmemd24/lib
```

`setup-binder-env` prepends the binder env to PATH at container startup. Biobb repos that install their own GROMACS or AmberTools via conda take priority -- correct behavior. Repos without MD tools fall back to image-installed binaries.

### Environment Variables in Final Image

```dockerfile
ENV AMBERHOME=/opt/ambertools25
ENV PATH="/opt/pmemd24/bin:/opt/ambertools25/bin:/opt/conda/envs/gromacs/bin:${PATH}"
ENV LD_LIBRARY_PATH=/opt/ambertools25/lib:/opt/pmemd24/lib
ENV CONDA_OVERRIDE_CUDA=12.0
```

### UX Impact

| Aspect | Behavior |
|--------|----------|
| Shell commands | `gmx`, `tleap`, `antechamber`, `sander`, `cpptraj`, `pmemd` are on global PATH |
| Biobb wrappers | Shell out via `subprocess` -- work transparently |
| Python packages | `parmed` lives in conda env, not importable by default. Most biobb workflows install their own conda env via binder; image binaries are a fallback. |
| Missing tools | `pdb4amber`, `reduce` not included. Installable via binder env if needed. Not blocking for MD workflows. |
| GPU | `pmemd.cuda` and `gmx mdrun -nb gpu` need NVIDIA Container Runtime at pod startup. Correct behavior. |

## Pod Changes

### Container count: 2 → 1

`create_notebook_pod` in `dashboard/api/clients/k8s.py` drops the gmx container spec. Pod spec has a single `jupyter` container.

### GPU attachment

`gpu=True` adds `nvidia.com/gpu: 1` to `notebook_resources` (jupyter container) instead of `gmx_resources` (former sidecar). Semantics of `Notebook.gpu` DB column unchanged -- boolean still means "attach GPU to this notebook." No migration needed.

### Resource model

| Before | After |
|--------|-------|
| `NOTEBOOK_RESOURCES` + `GMX_RESOURCES` | `NOTEBOOK_RESOURCES` only |
| Tier scaling multiplies two dicts | Tier scaling on one dict |
| Quota: sum both containers | Quota: single container |
| `get_tier_resources()` returns `(nb_res, gmx_res)` tuple | Returns single `nb_res` dict |

## Code Changes

### `notebook/Dockerfile`
- Add `amber` stage for `pmemd` binaries
- Install `gromacs=2026` and `ambertools` in dedicated conda envs
- Remove the existing `gmx` proxy script (no longer needed -- binary is local)
- Set `AMBERHOME`, `PATH`, `LD_LIBRARY_PATH` for bundled tools

### `dashboard/api/clients/k8s.py` -- `create_notebook_pod`
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
- Remove `gmxCpuRequest`, `gmxCpuLimit`, `gmxMemoryRequest`, `gmxMemoryLimit` from hub `extraEnv`
- Remove `GMX_IMAGE` from hub `extraEnv` (keep in `mdrun-api` env -- production jobs still use it)

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
- MDRun API: AMBER and GROMACS production jobs unaffected -- they already run as separate K8s Jobs using `GMX_IMAGE` from config
- Binder env setup scripts: no change
- Caddy proxy, auth service, JupyterHub config: no change
- `run-notebook.sh` pod self-deletion logic: no change

## Open Items for Implementation

1. ~~Inspect GROMACS image: `docker run --rm cerit.io/ljocha/gromacs:... ldd $(which gmx)` -- enumerate all non-CUDA `.so` deps and their paths~~ -- **Done:** Too complex (~4GB transitive deps), replaced with conda-forge install.
2. **Inspect AMBER image:** `docker run --rm cerit.io/xkrasa/amber:24 find /opt/pmemd24 -type d` -- verified: `bin`, `lib` directories exist. AmberTools tools (tleap, antechamber, etc.) must come from conda-forge, not this image.
3. **Verify `tleap` works** with `AMBERHOME=/opt/conda/envs/amber` by running a minimal tleap command in the built image -- **Done:** `tleap -v` exits cleanly with correct dat paths.
4. **Verify `gmx mdrun` GPU acceleration** works in built image with NVIDIA runtime (test on GPU node).
5. **Verify `pmemd.cuda` GPU acceleration** works when NVIDIA runtime mounts CUDA libs at pod startup.
6. **Test reduce workaround** if users report missing `--reduce` in `pdb4amber` workflows.
