FROM node:26-slim AS build

WORKDIR /app

RUN npm install -g pnpm@11.13.0 --quiet
COPY package.json pnpm-lock.yaml pnpm-workspace.yaml ./
COPY dashboard/ui/package.json dashboard/ui/package.json
COPY landing/package.json landing/package.json
COPY hub/ui/package.json hub/ui/package.json
RUN pnpm install --frozen-lockfile --filter landing...

COPY landing/ landing/
RUN pnpm --filter landing build

FROM caddy:2.11-alpine AS runtime

RUN apk add --no-cache libcap curl && setcap -r /usr/bin/caddy

RUN mkdir -p /config/caddy /data/caddy && \
    chown -R 1000:1000 /config /data

COPY --from=build /app/landing/dist /srv
COPY landing/Caddyfile /etc/caddy/Caddyfile

USER 1000

EXPOSE 8080

HEALTHCHECK --interval=30s --timeout=3s --start-period=5s --retries=3 \
    CMD curl --fail http://localhost:8080/health || exit 1

CMD ["caddy", "run", "--config", "/etc/caddy/Caddyfile", "--adapter", "caddyfile"]
