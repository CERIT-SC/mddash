#!/bin/bash

# Cleanup and signal handling utilities

LOG_DIR="/tmp/mddash-logs"

log() {
    echo "$(date): [CLEANUP] $1" >> "$LOG_DIR/cleanup.log"
    echo "$(date): [CLEANUP] $1"
}

cleanup_all() {
    log "Starting cleanup process..."

    /scripts/s3-setup.sh cleanup
    /scripts/services.sh stop

    log "Cleanup completed"
}

setup_signal_handlers() {
    log "Setting up signal handlers for graceful shutdown"

    # Create a cleanup function that can be called by signal handlers
    trap 'cleanup_all; exit 0' SIGTERM SIGINT
}


case "${1:-setup}" in
    "setup")
        setup_signal_handlers
        ;;
    "cleanup")
        cleanup_all
        ;;
    *)
        log "Usage: $0 {setup|cleanup}"
        exit 1
        ;;
esac
