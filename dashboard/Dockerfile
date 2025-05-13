FROM node:21 AS build-stage

WORKDIR /usr/src/app
COPY ./dash .

RUN npm install --force
RUN npm run build


FROM caddy:2.10-alpine AS caddy-stage


FROM alpine:3.21

# Install runtime dependencies for Flask, Kubernetes client, and Caddy
RUN apk add --no-cache \
    py3-flask \
    py3-kubernetes \
    ca-certificates \
    mailcap \
    tzdata


RUN adduser --disabled-password --uid 1000 jovyan


# Copy Caddy binary from caddy-stage
COPY --from=caddy-stage --chown=jovyan:jovyan /usr/bin/caddy /usr/bin/caddy

# Create Caddy files and set permissions for jovyan user
RUN mkdir -p /caddy/data /caddy/config
COPY ./Caddyfile /caddy
RUN chown -R jovyan:jovyan /caddy
RUN chmod 644 /caddy/Caddyfile

ENV XDG_DATA_HOME=/caddy/data
ENV XDG_CONFIG_HOME=/caddy/config

# Copy the API code and start script
COPY --chown=jovyan:jovyan ./api /opt/api
COPY --chown=jovyan:jovyan ./start.sh /start.sh
RUN chmod +x /start.sh

# Dash frontend app
COPY --from=build-stage --chown=jovyan:jovyan /usr/src/app/dist /opt/dash


USER jovyan

EXPOSE 8888

CMD ["/start.sh"]

# docker build -t cerit.io/ljocha/mddash . && docker push cerit.io/ljocha/mddash
