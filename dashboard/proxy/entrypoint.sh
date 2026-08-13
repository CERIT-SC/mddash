#!/bin/sh
set -eu

config_path=${CONFIG_PATH:-/config/runtime-config.json}

jq -n \
  --arg basePath "${CADDY_ROUTE_PREFIX}/dash" \
  --arg apiPath "${CADDY_ROUTE_PREFIX}/dash/api" \
  --arg user "${JUPYTERHUB_USER}" \
  --arg defaultNotebooksRepo "${DEFAULT_NOTEBOOKS_REPO}" \
  --arg mdpositUrl "${MDPOSIT_URL}" \
  '{basePath: $basePath, apiPath: $apiPath, user: $user,
    defaultNotebooksRepo: $defaultNotebooksRepo, mdpositUrl: $mdpositUrl,
    hubHomeUrl: "/hub/home", hubTokenUrl: "/hub/token", logoutUrl: "/hub/logout"}' > "$config_path"

if [ "${CONFIG_ONLY:-0}" = "1" ]; then
  exit 0
fi

exec caddy run --config /etc/caddy/Caddyfile --adapter caddyfile
