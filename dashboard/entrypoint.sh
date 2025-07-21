#!/bin/bash

# This script serves as the entrypoint for both JupyterHub single-user server
# and standalone dashboard modes

# Create log directory in a persistent location
mkdir -p /mddash/logs

# Log all output for debugging
exec >> /mddash/logs/entrypoint.log 2>&1

echo "$(date): Entrypoint started with args: $@"
echo "$(date): Environment variables:"
env | grep -E "(JUPYTERHUB|USER)" | sort

# Check if we're running under JupyterHub (presence of JUPYTERHUB_* environment variables)
if [ -n "$JUPYTERHUB_API_TOKEN" ] || [ -n "$JUPYTERHUB_SERVICE_PREFIX" ]; then
    echo "$(date): Running in JupyterHub mode"
    
    # Start dashboard services in background
    echo "$(date): Starting dashboard services..."
    
    # inject base path for dashboard
    echo "$(date): Injecting base path"
    BASE_PATH="${JUPYTERHUB_SERVICE_PREFIX}dash"
    API_PATH="${JUPYTERHUB_SERVICE_PREFIX}dash/api"

    echo "$(date): Base path: ${BASE_PATH}"
    echo "$(date): API path: ${API_PATH}"

    for f in $(cd /opt && find dash -type f); do
        mkdir -p $(dirname /var/tmp/$f)
        sed "s|/__BASE_PATH__|${BASE_PATH}|g; s|/__API_PATH__|${API_PATH}|g" /opt/$f >/var/tmp/$f
    done

    export CADDY_ROUTE_PREFIX="${JUPYTERHUB_SERVICE_PREFIX}"
    echo "$(date): Starting Caddy with route prefix ${CADDY_ROUTE_PREFIX}"
    caddy start --config /caddy/Caddyfile --adapter caddyfile > /mddash/logs/caddy.log 2>&1
    
    echo "$(date): Caddy start result: $?"
    sleep 2  # Give Caddy time to start
    
    echo "$(date): Starting API in background"
    python /opt/api/main.py > /mddash/logs/api.log 2>&1 &
    API_PID=$!
    echo "$(date): API started with PID: $API_PID"
    
    # Start JupyterHub single-user server
    echo "$(date): Starting JupyterHub single-user server"
    exec jupyterhub-singleuser \
        --ip=0.0.0.0 \
        --port=8889 \
        --allow-root \
        --notebook-dir=/home/jovyan \
        > /mddash/logs/jupyter.log 2>&1

else
    echo "$(date): Running in standalone mode"
    # Run the original start script for standalone mode
    exec /start.sh > /mddash/logs/standalone.log 2>&1
fi
