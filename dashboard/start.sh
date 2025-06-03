#!/bin/sh

# inject base path
echo "injecting base path"
BASE_PATH="/user/${JUPYTERHUB_USER}/dash"
API_PATH="/user/${JUPYTERHUB_USER}/api"
for f in $(cd /opt && find dash -type f); do
	mkdir -p $(dirname /var/tmp/$f)
	sed "s|/__BASE_PATH__|${BASE_PATH}|g; s|/__API_PATH__|${API_PATH}|g" /opt/$f >/var/tmp/$f
done

export CADDY_ROUTE_PREFIX="/user/${JUPYTERHUB_USER}"
echo "Starting Caddy with route prefix ${CADDY_ROUTE_PREFIX}"
caddy start --config /caddy/Caddyfile --adapter caddyfile

echo "starting API"
python /opt/api/main.py
