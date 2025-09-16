#!/bin/bash

# This script serves as the entrypoint for both JupyterHub single-user server
# and standalone dashboard modes

# Create local log directory (not in S3)
mkdir -p /tmp/mddash-logs

# Log all output for debugging
: > /tmp/mddash-logs/entrypoint.log
exec >> /tmp/mddash-logs/entrypoint.log 2>&1

echo "$(date): Environment variables:"
env | grep -E "(JUPYTERHUB|USER|NAMESPACE|S3)" | sort

# Cleanup function for graceful shutdown
cleanup() {
    echo "$(date): Cleaning up processes..."
    if [ -n "$API_PID" ]; then
        kill $API_PID 2>/dev/null || true
    fi
    
    # Stop rclone sync daemon if running
    if [ -n "$RCLONE_SYNC_PID" ]; then
        echo "$(date): Stopping rclone sync daemon..."
        kill $RCLONE_SYNC_PID 2>/dev/null || true
        # Final sync before shutdown
        echo "$(date): Final sync to S3..."
        rclone sync /mddash s3remote:${S3_BUCKET} --create-empty-src-dirs 2>/dev/null || true
    fi
    
    caddy stop 2>/dev/null || true
    exit 0
}

# Set up signal handlers
trap cleanup SIGTERM SIGINT

# Mount S3 as /mddash if S3 variables are present
if [ -n "$S3_BUCKET" ]; then
    echo "$(date): Setting up S3 bucket ${S3_BUCKET} as /mddash"

    # Create rclone config
    mkdir -p /home/jovyan/.config/rclone
    cat > /home/jovyan/.config/rclone/rclone.conf << EOF
[s3remote]
type = s3
provider = Other
access_key_id = ${S3_ACCESS_KEY}
secret_access_key = ${S3_SECRET_KEY}
endpoint = ${S3_ENDPOINT}
EOF

    # Create mount point and cache directory
    mkdir -p /mddash
    mkdir -p /home/jovyan/.cache/rclone

    # Since FUSE is not available, use rclone sync for filesystem-like access
    echo "$(date): Setting up S3 access via rclone sync (no FUSE required)"
    
    # Ensure S3 bucket exists
    echo "$(date): Creating S3 bucket if it doesn't exist"
    rclone mkdir s3remote:${S3_BUCKET} 2>/dev/null || echo "$(date): Bucket creation failed or already exists"
    
    # Initial sync from S3 to local directory
    echo "$(date): Initial sync from S3 to /mddash"  
    rclone sync s3remote:${S3_BUCKET} /mddash --create-empty-src-dirs --log-level INFO --log-file /tmp/mddash-logs/rclone-sync.log
    
    # Start background bidirectional sync
    echo "$(date): Starting background S3 sync daemon"
    (
        while true; do
            # Sync local changes to S3 (upload)
            rclone sync /mddash s3remote:${S3_BUCKET} --create-empty-src-dirs --log-level ERROR
            # Sync S3 changes to local (download) 
            rclone sync s3remote:${S3_BUCKET} /mddash --create-empty-src-dirs --log-level ERROR
            sleep 10
        done
    ) > /tmp/mddash-logs/rclone-sync-daemon.log 2>&1 &
    RCLONE_SYNC_PID=$!
    echo "$(date): Background sync started with PID: $RCLONE_SYNC_PID"

    # Verify sync completed and directory is ready
    if [ -d "/mddash" ]; then
        echo "$(date): S3 sync setup complete, /mddash is ready"
        ls -la /mddash/ || echo "$(date): Directory exists but may be empty (new bucket)"
    else
        echo "$(date): ERROR - Failed to set up /mddash directory"
        mkdir -p /mddash
    fi
else
    echo "$(date): No S3 configuration found, using local /mddash"
    mkdir -p /mddash
fi

# Remove trailing slash
JH_PREFIX="${JUPYTERHUB_SERVICE_PREFIX%/}"

echo "$(date): Injecting base path"
BASE_PATH="${JH_PREFIX}/dash"
API_PATH="${JH_PREFIX}/dash/api"

echo "$(date): Base path: ${BASE_PATH}"
echo "$(date): API path: ${API_PATH}"

for f in $(cd /opt && find dash -type f); do
    mkdir -p $(dirname /var/tmp/$f)
    sed "s|/__BASE_PATH__|${BASE_PATH}|g; s|/__API_PATH__|${API_PATH}|g" /opt/$f >/var/tmp/$f
done

export CADDY_ROUTE_PREFIX="${JH_PREFIX}"
echo "$(date): Starting Caddy with route prefix ${CADDY_ROUTE_PREFIX}"
caddy start --config /caddy/Caddyfile --adapter caddyfile > /tmp/mddash-logs/caddy.log 2>&1

echo "$(date): Starting API in background"
python /opt/api/app.py > /tmp/mddash-logs/api.log 2>&1 &
API_PID=$!
echo "$(date): API started with PID: $API_PID"

# Start JupyterHub single-user server
echo "$(date): Starting JupyterHub single-user server"
exec jupyterhub-singleuser \
    --ip=0.0.0.0 \
    --port=8889 \
    --allow-root \
    --notebook-dir=/home/jovyan \
    > /tmp/mddash-logs/jupyter.log 2>&1
