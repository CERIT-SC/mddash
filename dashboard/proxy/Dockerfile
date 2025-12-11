# Proxy container - Caddy reverse proxy with static UI files
# Build arg UI_IMAGE should point to the pre-built UI image

ARG UI_IMAGE=mddash-ui:latest

FROM ${UI_IMAGE} AS ui

FROM caddy:2.10-alpine

# Remove cap_net_bind_service - Caddy won't bind privileged ports
RUN apk add --no-cache libcap curl && setcap -r /usr/bin/caddy

RUN mkdir -p /config/caddy /data/caddy && \
    chown -R 1000:1000 /config /data

COPY --from=ui /dist /opt/dash
COPY Caddyfile /etc/caddy/Caddyfile

USER 1000

EXPOSE 8888

HEALTHCHECK --interval=30s --timeout=3s --start-period=5s --retries=3 \
    CMD curl --fail http://localhost:8888/health || exit 1

CMD ["caddy", "run", "--config", "/etc/caddy/Caddyfile", "--adapter", "caddyfile"]
