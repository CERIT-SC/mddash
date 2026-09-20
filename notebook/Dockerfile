FROM cerit.io/mddash/amber:26 AS amber

FROM quay.io/jupyter/base-notebook:2026-09-18 AS base

# Amber runtime prune (own stage: files deleted here never reach the final image).
# cuda-12.8 is 2.8 GB but pmemd.cuda NEEDs only 8 lib families; nvrtc kept for JIT.
FROM base AS amber-runtime
USER root
COPY --from=amber /opt/ambertools26 /opt/ambertools26
COPY --from=amber /opt/pmemd26      /opt/pmemd26
COPY --from=amber /usr/local/cuda-12.8 /usr/local/cuda-12.8
RUN CUL=/usr/local/cuda-12.8/targets/x86_64-linux/lib \
    && find $CUL -maxdepth 1 -type f -name 'lib*.so*' \
            ! -name 'libcublas.*' ! -name 'libcublasLt.*' ! -name 'libcufft.*' \
            ! -name 'libcurand.*' ! -name 'libcusolver.*' ! -name 'libcusparse.*' \
            ! -name 'libnvJitLink.*' ! -name 'libnvrtc*' -delete \
    && find /usr/local/cuda-12.8 -xtype l -delete \
    && rm -rf /usr/local/cuda-12.8/compat \
    && find /opt/ambertools26 /opt/pmemd26 -name '*.a' -delete \
    && find /opt/ambertools26 -name '__pycache__' -type d -prune -exec rm -rf {} +

FROM base

USER root

RUN apt-get update && apt-get install -y --no-install-recommends \
    curl vim git build-essential python3-dev rsync libgfortran5 \
    fontconfig fonts-dejavu-core \
    && fc-cache -f \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# Keep within one minor of the cluster's API server (kubectl version skew policy).
ARG KUBECTL_VERSION=v1.34.11
RUN curl -fLOsS "https://dl.k8s.io/release/${KUBECTL_VERSION}/bin/linux/amd64/kubectl" \
    && install -m 755 kubectl /usr/local/bin/kubectl \
    && rm kubectl

COPY --from=amber-runtime /opt/ambertools26 /opt/ambertools26
COPY --from=amber-runtime /opt/pmemd26      /opt/pmemd26
COPY --from=amber-runtime /usr/local/cuda-12.8 /usr/local/cuda-12.8
RUN ln -s /usr/local/cuda-12.8 /usr/local/cuda

# tleap resolves force field parameters via AMBERHOME
ENV AMBERHOME=/opt/ambertools26

# PATH: pmemd/AmberTools CLIs are available globally, but notebook/base conda
# and Binder envs must keep priority over AmberTools' embedded miniconda.
ENV PATH="/opt/pmemd26/bin:/opt/ambertools26/bin:/opt/conda/envs/gromacs/bin:${PATH}:/opt/ambertools26/miniconda/bin"
ENV LD_LIBRARY_PATH=/opt/ambertools26/lib:/opt/pmemd26/lib:/opt/ambertools26/miniconda/lib:/usr/local/cuda/lib64
ENV AMBER_PYTHONPATH=/opt/ambertools26/miniconda/lib/python3.12/site-packages:/opt/ambertools26/lib/python3.12/site-packages

# Over-prune guard; nvrtc is a JIT hedge — dlopen'd libs never appear in ldd.
RUN readelf -d /opt/pmemd26/bin/pmemd.cuda >/dev/null \
    && ldd /opt/pmemd26/bin/pmemd.cuda > /tmp/pmemd-ldd.out \
    && ! grep -q "not found" /tmp/pmemd-ldd.out

# Installs run as $NB_USER: the base image owns /opt/conda as jovyan, so files get the
# right ownership natively — no chown -R sweeps (which would duplicate whole layers).
USER 1000

# GROMACS via conda-forge. `nompi_cuda*` build-string pin is REQUIRED: the default build is
# OpenCL, blind to this cluster's NVIDIA GPUs; CONDA_OVERRIDE_CUDA only registers the
# virtual __cuda package (no GPU at build time), driver libs mount at pod start. The prune
# keeps only runtime-linked libs — over-pruning fails the `gmx --version` assert (NEEDED
# libs resolve at exec time).
ENV CONDA_OVERRIDE_CUDA=12.0
RUN GX=/opt/conda/envs/gromacs \
    && mamba create -n gromacs -c conda-forge -y "gromacs=2026=nompi_cuda*" \
    && mamba clean -afy \
    && find $GX -name '*.a' -delete \
    && find $GX/targets/x86_64-linux/lib -maxdepth 1 -type f -name 'lib*.so*' \
            ! -name 'libcufft*' ! -name 'libcudart*' -delete \
    && rm -rf $GX/targets/x86_64-linux/lib/stubs \
              $GX/targets/x86_64-linux/lib/cmake \
              $GX/targets/x86_64-linux/lib/pkgconfig \
    && rm -rf $GX/nvvm $GX/libnvvp $GX/nsightee_plugins $GX/nsight-compute-* \
    && rm -f $GX/bin/ptxas $GX/bin/cicc $GX/bin/cudafe++ $GX/bin/cuobjdump \
             $GX/bin/fatbinary $GX/bin/nvdisasm $GX/bin/nvlink $GX/bin/ncu $GX/bin/ncu-ui \
             $GX/bin/nsys $GX/bin/nsys-ui $GX/bin/nvprof $GX/bin/cuda-gdb* \
             $GX/bin/nvcc* $GX/bin/nsight* $GX/bin/compute-sanitizer \
    && find $GX -xtype l -delete \
    && $GX/bin/gmx --version | grep -q "GPU support:.*CUDA"

COPY --chown=1000:1000 requirements.txt /tmp/
RUN python -m pip install --no-cache-dir -r /tmp/requirements.txt \
    && rm /tmp/requirements.txt

COPY --chown=1000:1000 jupyterlab-pipeline-tracker /tmp/jupyterlab-pipeline-tracker
RUN python -m pip install --no-cache-dir --no-build-isolation /tmp/jupyterlab-pipeline-tracker \
    && rm -rf /tmp/jupyterlab-pipeline-tracker \
    && jupyter labextension list

COPY --chown=1000:1000 --chmod=755 setup-binder-env     /usr/local/bin/before-notebook.d/setup-binder-env
COPY --chown=1000:1000 --chmod=755 start-with-binder.sh /usr/local/bin/start-with-binder.sh
COPY --chown=1000:1000 --chmod=755 run-notebook.sh      /usr/local/bin/run-notebook.sh
