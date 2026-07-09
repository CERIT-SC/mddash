FROM cerit.io/xkrasa/amber:26 AS amber

FROM quay.io/jupyter/base-notebook:2026-06-29

USER root

RUN apt-get update && apt-get install -y \
    curl vim git build-essential python3-dev rsync libgfortran5 \
    fontconfig fonts-dejavu-core \
    && fc-cache -f \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# K8s fsGroup compatibility: jovyan must be in group 1000
RUN groupadd -f -g 1000 jovyan && usermod -aG jovyan jovyan

RUN curl -LOs "https://dl.k8s.io/release/$(curl -Ls https://dl.k8s.io/release/stable.txt)/bin/linux/amd64/kubectl" \
    && install -m 755 kubectl /usr/local/bin/kubectl \
    && rm kubectl

# GROMACS via conda-forge.  CONDA_OVERRIDE_CUDA allows CUDA builds to install
# without a GPU present at build time; NVIDIA Container Runtime mounts real
# CUDA libs at pod startup.
ENV CONDA_OVERRIDE_CUDA=12.0
RUN mamba create -n gromacs -c conda-forge -y gromacs=2026 \
    && mamba clean -afy

COPY --from=amber /opt/ambertools26 /opt/ambertools26
COPY --from=amber /opt/pmemd26      /opt/pmemd26
COPY --from=amber /usr/local/cuda-12.8 /usr/local/cuda-12.8
RUN ln -s /usr/local/cuda-12.8 /usr/local/cuda

# tleap resolves force field parameters via AMBERHOME
ENV AMBERHOME=/opt/ambertools26

# PATH: pmemd/AmberTools CLIs are available globally, but notebook/base conda
# and Binder envs must keep priority over AmberTools' embedded miniconda.
ENV PATH="/opt/pmemd26/bin:/opt/ambertools26/bin:/opt/conda/envs/gromacs/bin:${PATH}:/opt/ambertools26/miniconda/bin"
ENV LD_LIBRARY_PATH=/opt/ambertools26/lib:/opt/pmemd26/lib:/opt/ambertools26/miniconda/lib:/usr/local/cuda/lib64
ENV AMBER_PYTHONPATH=/opt/ambertools26/miniconda/lib/python3.12/site-packages:/opt/ambertools26/lib/python3.12/site-packages

COPY requirements.txt /tmp/
RUN python -m pip install --no-cache-dir -r /tmp/requirements.txt \
    && rm /tmp/requirements.txt

COPY jupyterlab-pipeline-tracker /tmp/jupyterlab-pipeline-tracker
RUN python -m pip install --no-cache-dir --no-build-isolation /tmp/jupyterlab-pipeline-tracker \
    && rm -rf /tmp/jupyterlab-pipeline-tracker \
    && jupyter labextension list \
    && chown -R "${NB_USER}:users" "${CONDA_DIR}" "/home/${NB_USER}"

COPY --chown=1000:1000 --chmod=755 setup-binder-env     /usr/local/bin/before-notebook.d/setup-binder-env
COPY --chown=1000:1000 --chmod=755 start-with-binder.sh /usr/local/bin/start-with-binder.sh
COPY --chown=1000:1000 --chmod=755 run-notebook.sh      /usr/local/bin/run-notebook.sh

USER 1000
