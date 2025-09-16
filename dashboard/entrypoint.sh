#!/bin/bash

# This script serves as the entrypoint for JupyterHub single-user server

echo "$(date): [MAIN] Starting MDDash entrypoint..."

# Initialize logging system
/scripts/logging.sh setup

echo "$(date): [MAIN] Setting up signal handlers..."
/scripts/cleanup.sh setup

echo "$(date): [MAIN] Setting up S3..."
/scripts/s3-setup.sh setup
if [ $? -ne 0 ]; then
    echo "$(date): [MAIN] ERROR: S3 setup failed"
    exit 1
fi

echo "$(date): [MAIN] Starting S3 sync daemon..."
/scripts/s3-setup.sh start-daemon

echo "$(date): [MAIN] Starting services..."
/scripts/services.sh start-all
