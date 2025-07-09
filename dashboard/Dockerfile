FROM node:24-slim AS build-stage

WORKDIR /usr/src/app
COPY ./dash .

RUN npm install --force
RUN npm run build


FROM caddy:2.10-alpine AS caddy-stage


FROM alpine:3.21

# Install runtime dependencies for Flask, Kubernetes client, and Python
RUN apk add --no-cache \
    py3-flask \
    py3-kubernetes \
    py3-pip \
    ca-certificates \
    mailcap \
    tzdata

# Install build dependencies, JupyterHub packages, then clean up
RUN apk add --no-cache --virtual .build-deps \
    gcc \
    python3-dev \
    musl-dev \
    linux-headers \
    && pip install --no-cache-dir --break-system-packages \
        'jupyterhub>=3.0,<4.0' \
        'notebook>=6.4,<7.0' \
        'jupyter-server>=1.21,<2.0' \
    && apk del .build-deps

RUN adduser --disabled-password --uid 1000 jovyan

# Create home directory and set permissions
RUN mkdir -p /home/jovyan && chown jovyan:jovyan /home/jovyan

# Create necessary directories for JupyterHub
RUN mkdir -p /mddash/logs && chown jovyan:jovyan /mddash/logs


# Copy Caddy binary from caddy-stage
COPY --from=caddy-stage --chown=jovyan:jovyan /usr/bin/caddy /usr/bin/caddy

# Create Caddy files and set permissions for jovyan user
RUN mkdir -p /caddy/data /caddy/config
COPY ./Caddyfile /caddy
RUN chown -R jovyan:jovyan /caddy
RUN chmod 644 /caddy/Caddyfile

ENV XDG_DATA_HOME=/caddy/data
ENV XDG_CONFIG_HOME=/caddy/config

# Copy the API code and start scripts
COPY --chown=jovyan:jovyan ./api /opt/api
COPY --chown=jovyan:jovyan ./start.sh /start.sh
COPY --chown=jovyan:jovyan ./entrypoint.sh /entrypoint.sh
RUN chmod +x /start.sh /entrypoint.sh

# Dash frontend app
COPY --from=build-stage --chown=jovyan:jovyan /usr/src/app/dist /opt/dash


USER jovyan

EXPOSE 8888

# Set the new entrypoint that handles both JupyterHub and standalone modes
ENTRYPOINT ["/entrypoint.sh"]

CMD ["/start.sh"]

# docker build -t cerit.io/ljocha/mddash . && docker push cerit.io/ljocha/mddash
