FROM node:21 AS build-stage

WORKDIR /usr/src/app
COPY ./dash .

RUN npm install --force
RUN npm run build


FROM caddy:2.10-builder-alpine AS caddy-stage

RUN xcaddy build


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
COPY --from=caddy-stage /usr/bin/caddy /usr/bin/caddy

# Create Caddy directories and set permissions for jovyan user
RUN mkdir -p /etc/caddy /data/caddy /var/tmp && \
    chown -R jovyan:jovyan /etc/caddy /data/caddy /var/tmp

# Copy Caddyfile
COPY --chown=jovyan:jovyan ./Caddyfile /etc/caddy/Caddyfile
RUN chmod 644 /etc/caddy/Caddyfile

COPY --chown=jovyan:jovyan ./api /opt/api
COPY --chown=jovyan:jovyan ./start.sh /start.sh
RUN chmod +x /start.sh

# Dash frontend app
COPY --from=build-stage --chown=jovyan:jovyan /usr/src/app/dist /opt/dash


USER jovyan

EXPOSE 8888

CMD ["/start.sh"]

# docker build -t cerit.io/ljocha/mddash . && docker push cerit.io/ljocha/mddash
