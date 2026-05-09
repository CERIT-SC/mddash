FROM cerit.io/xkrasa/amber:24 AS amber

FROM quay.io/jupyter/base-notebook:latest

USER root

RUN apt-get update && apt-get install -y \
    curl vim git build-essential python3-dev rsync libgfortran5 \
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

COPY --from=amber /opt/ambertools25 /opt/ambertools25
COPY --from=amber /opt/pmemd24      /opt/pmemd24

# tleap resolves force field parameters via AMBERHOME
ENV AMBERHOME=/opt/ambertools25

# PATH: pmemd > AmberTools > GROMACS.  Binder env prepended by setup-binder-env
# takes priority -- correct fallback for repos that install their own tools.
ENV PATH="/opt/pmemd24/bin:/opt/ambertools25/bin:/opt/conda/envs/gromacs/bin:${PATH}"
ENV LD_LIBRARY_PATH=/opt/ambertools25/lib:/opt/pmemd24/lib

COPY requirements.txt /tmp/
RUN python -m pip install --no-cache-dir -r /tmp/requirements.txt \
    && rm /tmp/requirements.txt \
    && chown -R "${NB_USER}:users" "${CONDA_DIR}" "/home/${NB_USER}"

COPY --chown=1000:1000 --chmod=755 setup-binder-env     /usr/local/bin/before-notebook.d/setup-binder-env
COPY --chown=1000:1000 --chmod=755 start-with-binder.sh /usr/local/bin/start-with-binder.sh
COPY --chown=1000:1000 --chmod=755 run-notebook.sh      /usr/local/bin/run-notebook.sh

USER 1000
