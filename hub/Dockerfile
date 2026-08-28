# MDDash JupyterHub image: stock k8s-hub + the EGI authenticator package
# (provides /hub/jwt_login, pinned to the same commit as the previously used
# eginotebooks/hub image) + the compiled hub-ui (login/home/spawn/… pages).

FROM node:26-slim AS build

WORKDIR /app

RUN npm install -g pnpm@11.13.0 --quiet
COPY package.json pnpm-lock.yaml pnpm-workspace.yaml ./
COPY dashboard/ui/package.json dashboard/ui/package.json
COPY landing/package.json landing/package.json
COPY hub/ui/package.json hub/ui/package.json
RUN pnpm install --frozen-lockfile --filter hub-ui...

COPY hub/ui/ hub/ui/
RUN pnpm --filter hub-ui build

# Separate rendered-at-runtime templates from static assets.
RUN mkdir -p /out/tpl /out/static && \
    cp hub/ui/dist/*.html /out/tpl/ && \
    cp -r hub/ui/dist/assets /out/static/assets

FROM quay.io/jupyterhub/k8s-hub:4.4.0 AS runtime

ARG EGI_HUB_REF=4ffff9e582b3e0ffb2b41e3ec14087d350402037
# k8s-hub 4.4.0 defaults to a non-root user; install the package system-wide.
USER root
# egi-notebooks-hub uses pbr-derived versions; give it a deterministic version
# when building from a raw commit archive.
RUN PBR_VERSION=1.0.0 pip3 install --no-cache-dir \
    "egi-notebooks-hub @ git+https://github.com/EGI-Federation/egi-notebooks-hub.git@${EGI_HUB_REF}"

# JupyterHub renders these with Jinja (path already in template_paths config).
COPY --from=build /out/tpl/ /opt/jupyterhub/custom-templates/
# Served by the hub at /hub/static/hub-ui/… (Vite base path).
COPY --from=build /out/static/ /usr/local/share/jupyterhub/static/hub-ui/

USER 1000
