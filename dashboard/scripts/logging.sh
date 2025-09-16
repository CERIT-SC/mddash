#!/bin/bash

# Logging utilities

LOG_DIR="/tmp/mddash-logs"

setup_logging() {
    # Create local log directory (not in S3)
    mkdir -p "$LOG_DIR"

    # Initialize main log file
    : > "$LOG_DIR/entrypoint.log"

    # Log all output for debugging
    exec >> "$LOG_DIR/entrypoint.log" 2>&1

    echo "$(date): [LOGGING] Logging system initialized"
    echo "$(date): [LOGGING] Log directory: $LOG_DIR"
}

log_environment() {
    echo "$(date): [LOGGING] Environment variables:"
    env | grep -E "(JUPYTERHUB|USER|NAMESPACE|S3)" | sort >> "$LOG_DIR/environment.log"
    echo "$(date): [LOGGING] Environment logged to $LOG_DIR/environment.log"
}


case "${1:-setup}" in
    "setup")
        setup_logging
        log_environment
        ;;
    *)
        echo "Usage: $0 {setup}"
        exit 1
        ;;
esac
