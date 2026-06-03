# Notebook Image

This image is the user-facing compute environment for MDDash. Treat it as a reproducible scientific workstation, not just a Jupyter server: users should find the MD tools, notebook UI extensions, and repository-specific dependencies ready when their pod starts.

## Philosophy

- Prefer image-baked capabilities for platform-wide tools, especially anything large, slow to install, GPU-sensitive, or required by many users.
- Keep per-experiment dependencies in the user PVC when they come from Binder files. Binder support is intentionally runtime-driven so imported repositories can bring their own environment without rebuilding the platform image.
- Preserve the Jupyter base-notebook startup contract. Hooks in `before-notebook.d/` and `start-notebook.py` behavior matter because JupyterHub relies on the upstream image conventions.
- Avoid making AmberTools' embedded miniconda the active Python. Its binaries must be available, but `/opt/conda` and Binder environments should remain the notebook Python/runtime priority.

## Non-Obvious Components

- `setup-binder-env` runs automatically before notebook startup. It detects `binder/`, `environment.yml`, `requirements.txt`, or `postBuild`, creates `${WORKDIR}/.binder-env` on the PVC, registers it as the default `python3` kernel, and only marks success after all install steps complete.
- `start-with-binder.sh` activates the persisted Binder environment if the success marker exists. Failed Binder installs intentionally fall back to the base image and retry on the next pod start.
- `run-notebook.sh` deletes the current pod after Jupyter exits when `MY_POD_NAME` is present, releasing Kubernetes resources after idle shutdown or crashes.
- GROMACS is installed in a dedicated conda env and placed on `PATH`. CUDA-capable builds are installed without a build-time GPU; runtime CUDA libraries come from the cluster/NVIDIA runtime.
- AMBER and AmberTools are copied from the Amber image, including `pmemd`, AmberTools CLIs, and CUDA libraries. `AMBERHOME`, `LD_LIBRARY_PATH`, and `AMBER_PYTHONPATH` are set so tools like `tleap` can resolve force fields.
- `jupyterlab-pipeline-tracker` is installed from a trimmed prebuilt JupyterLab extension package. Keep only the Python packaging files and prebuilt `labextension/` assets unless the image needs to rebuild the TypeScript extension.
