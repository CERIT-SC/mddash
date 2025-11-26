#!/bin/sh
set -euo pipefail

echo "$(date): [PROXY] Starting proxy container..."

# Inject base path into static files
JH_PREFIX="${JUPYTERHUB_SERVICE_PREFIX%/}"
BASE_PATH="${JH_PREFIX}/dash"
API_PATH="${JH_PREFIX}/dash/api"

echo "$(date): [PROXY] Injecting base path: ${BASE_PATH}"
echo "$(date): [PROXY] Injecting API path: ${API_PATH}"

for f in $(cd /opt && find dash -type f); do
    mkdir -p "$(dirname "/var/tmp/$f")"
    sed "s|/__BASE_PATH__|${BASE_PATH}|g; s|/__API_PATH__|${API_PATH}|g" "/opt/$f" > "/var/tmp/$f"
done

export CADDY_ROUTE_PREFIX="${JH_PREFIX}"
echo "$(date): [PROXY] Route prefix set to: ${CADDY_ROUTE_PREFIX}"

echo "$(date): [PROXY] Starting Caddy..."
exec caddy run --config /caddy/Caddyfile --adapter caddyfile
