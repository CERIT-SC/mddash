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
- The `OMP_NUM_THREADS` unset in `run-notebook.sh` must stay image-side: the value comes from a cluster webhook (outside this repo) that preserves any pod-spec value — `""`/`"0"`/`"auto"` are all fatal with GPUs (tested live), only absence works. Do not re-add OMP handling to `dashboard/api` pod specs.
- `/opt/conda` is jovyan-owned in the base image, so installs run as `USER 1000` with no chown needed — a chown/prune in a later layer re-serializes everything it touches; prune in the create RUN or the `amber-runtime` stage.
- `jupyterlab-pipeline-tracker` keeps its full source in-repo (`src/`, `style/`, `tsconfig.json`, `package.json`, `test-notebooks/`) and is owned under repository standards: the Python packaging and the validation notebooks are covered by root `ruff` like any other code (ruff checks `.ipynb` by default; its formatting touches code cells only, never the cell structure, headings, markers, or metadata the discovery modes validate). The notebook image still installs the committed prebuilt `jupyterlab_pipeline_tracker/labextension/` assets — `notebook/.dockerignore` trims the image build context to the pip-install inputs. The federated bundle is rebuilt on-demand (`npm ci && npm run build` in `jupyterlab-pipeline-tracker/`) with the regenerated assets committed; never wire the TS build into CI or the image build.
