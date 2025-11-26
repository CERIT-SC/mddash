#!/bin/bash

# Service management script for Caddy, API, and JupyterHub

LOG_DIR="/tmp/mddash-logs"

log() {
    echo "$(date): [SERVICES] $1" >> "$LOG_DIR/services.log"
    echo "$(date): [SERVICES] $1"
}

setup_caddy_env() {
    # Set up environment variables for Caddy's dynamic config.js
    local jh_prefix="${JUPYTERHUB_SERVICE_PREFIX%/}"
    export CADDY_ROUTE_PREFIX="${jh_prefix}"
    log "Route prefix set to: ${CADDY_ROUTE_PREFIX}"
}

start_caddy() {
    log "Starting Caddy with route prefix ${CADDY_ROUTE_PREFIX}"
    caddy start --config /caddy/Caddyfile --adapter caddyfile > "$LOG_DIR/caddy.log" 2>&1
    
    if [ $? -eq 0 ]; then
        log "Caddy started successfully"
        return 0
    else
        log "ERROR: Failed to start Caddy"
        return 1
    fi
}

start_api() {
    log "Starting API in background"
    python /opt/api/app.py > "$LOG_DIR/api.log" 2>&1 &

    local api_pid=$!
    echo "$api_pid" > "$LOG_DIR/api.pid"
    log "API started with PID: $api_pid"

    return 0
}

start_forward_auth() {
    log "Starting Forward Auth in background"
    python /opt/auth/auth.py > "$LOG_DIR/forward-auth.log" 2>&1 &
    local auth_pid=$!
    echo "$auth_pid" > "$LOG_DIR/forward-auth.pid"
    log "Forward Auth started with PID: $auth_pid"
    return 0
}

start_jupyterhub() {
    log "Starting JupyterHub single-user server"
    exec jupyterhub-singleuser \
        --ip=0.0.0.0 \
        --port=8889 \
        --allow-root \
        --notebook-dir=/home/jovyan \
        > "$LOG_DIR/jupyter.log" 2>&1
}

stop_services() {
    log "Stopping services..."

    # Stop API
    if [ -f "$LOG_DIR/api.pid" ]; then
        local api_pid=$(cat "$LOG_DIR/api.pid")
        if [ -n "$api_pid" ]; then
            log "Stopping API (PID: $api_pid)..."
            kill $api_pid 2>/dev/null || true
            rm -f "$LOG_DIR/api.pid"
        fi
    fi

    # Stop Caddy
    log "Stopping Caddy..."
    caddy stop >> "$LOG_DIR/caddy-stop.log" 2>&1 || true
}

# Main execution
case "${1:-start-all}" in
    "setup-env")
        setup_caddy_env
        ;;
    "start-caddy")
        start_caddy
        ;;
    "start-api")
        start_api
        ;;
    "start-jupyter")
        start_jupyterhub
        ;;
    "start-all")
        setup_caddy_env
        start_forward_auth
        start_caddy
        start_api
        start_jupyterhub
        ;;
    "stop")
        stop_services
        ;;
    *)
        log "Usage: $0 {setup-env|start-caddy|start-api|start-jupyter|start-all|stop}"
        exit 1
        ;;
esac
