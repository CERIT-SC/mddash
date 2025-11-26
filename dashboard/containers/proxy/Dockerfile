FROM node:24-slim AS build-stage
WORKDIR /usr/src/app

COPY ./dash/package*.json ./
RUN npm install --force

COPY ./dash .
RUN npm run build

FROM caddy:2.10-alpine

# remove cap_net_bind_service because caddy will not be binding privileged ports
RUN apk add --no-cache libcap && setcap -r /usr/bin/caddy

# Create non-root user
RUN adduser -D -u 1000 -g 1000 appuser && \
    mkdir -p /caddy/data /caddy/config /var/tmp/dash && \
    chown -R 1000:1000 /caddy /var/tmp

COPY --from=build-stage --chown=1000:1000 /usr/src/app/dist /opt/dash
COPY --chown=1000:1000 ./containers/proxy/Caddyfile /caddy/
COPY --chown=1000:1000 ./containers/proxy/entrypoint.sh /entrypoint.sh

RUN chmod +x /entrypoint.sh

ENV XDG_DATA_HOME=/caddy/data
ENV XDG_CONFIG_HOME=/caddy/config

USER 1000

EXPOSE 8888

ENTRYPOINT ["/entrypoint.sh"]
