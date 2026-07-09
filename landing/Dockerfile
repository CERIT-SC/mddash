FROM node:26-alpine AS build

WORKDIR /app

RUN npm install -g pnpm@11.9.0 --quiet
COPY package.json pnpm-lock.yaml pnpm-workspace.yaml ./
RUN pnpm install --frozen-lockfile

COPY . .
RUN pnpm run build

FROM caddy:2.11-alpine AS runtime

RUN apk add --no-cache libcap curl && setcap -r /usr/bin/caddy

RUN mkdir -p /config/caddy /data/caddy && \
    chown -R 1000:1000 /config /data

COPY --from=build /app/dist /srv
COPY Caddyfile /etc/caddy/Caddyfile

USER 1000

EXPOSE 8080

HEALTHCHECK --interval=30s --timeout=3s --start-period=5s --retries=3 \
    CMD curl --fail http://localhost:8080/health || exit 1

CMD ["caddy", "run", "--config", "/etc/caddy/Caddyfile", "--adapter", "caddyfile"]
