FROM node:24-slim AS build-stage
WORKDIR /usr/src/app
COPY ./dash .
RUN npm install --force && npm run build

FROM caddy:2.10-alpine AS caddy-stage

FROM quay.io/jupyterhub/singleuser:5

USER root

# api requirements
COPY ./api/requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir -r /tmp/requirements.txt && rm /tmp/requirements.txt

RUN mkdir -p /mddash/logs /caddy/data /caddy/config \
    && chown -R jovyan:users /mddash /caddy

COPY --from=caddy-stage --chown=jovyan:users /usr/bin/caddy /usr/bin/caddy
COPY --from=build-stage --chown=jovyan:users /usr/src/app/dist /opt/dash
COPY --chown=jovyan:users ./api /opt/api
COPY --chown=jovyan:users ./Caddyfile /caddy/
COPY --chown=jovyan:users ./start.sh /start.sh
COPY --chown=jovyan:users ./entrypoint.sh /entrypoint.sh

RUN chmod +x /start.sh /entrypoint.sh

# caddy environment variables
ENV XDG_DATA_HOME=/caddy/data
ENV XDG_CONFIG_HOME=/caddy/config


USER jovyan

EXPOSE 8888

# Set the new entrypoint that handles both JupyterHub and standalone modes
ENTRYPOINT ["/entrypoint.sh"]

CMD ["/start.sh"]

# docker build -t cerit.io/ljocha/mddash . && docker push cerit.io/ljocha/mddash
