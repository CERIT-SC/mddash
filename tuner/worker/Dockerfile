# Source Dockerfile: https://github.com/ljocha/gromacs-plumed-docker/blob/master/Dockerfile

# Stage 1: Pull AMBER binaries from private licensed image (run `make push-amber` first).
ARG AMBER_IMAGE=cerit.io/mddash/amber:26
FROM ${AMBER_IMAGE} AS amber

# Stage 2: Combined GMX + AMBER worker
FROM cerit.io/ljocha/gromacs:2026-1-plumed-2-10-afed-pytorch-model-cv-2_ray-2-54-0_1

COPY --from=amber /opt/pmemd26 /opt/pmemd26
ENV AMBERHOME=/opt/pmemd26
ENV PATH="${AMBERHOME}/bin:${PATH}"
# AMBER bundles FFTW in lib/; ENV vars don't transfer with COPY --from.
ENV LD_LIBRARY_PATH="${AMBERHOME}/lib:${LD_LIBRARY_PATH}"

RUN apt-get update && apt-get install -y --no-install-recommends libgfortran5 && rm -rf /var/lib/apt/lists/*

COPY requirements.txt /tmp/requirements.txt
RUN pip install -r /tmp/requirements.txt --no-cache-dir && rm /tmp/requirements.txt

# Verify both engines are available at build time
RUN gmx --version && pmemd.cuda --version && pmemd.MPI --version

USER 1000
