#!/bin/bash
set -euo pipefail

LOG_DIR="/tmp/mddash-logs"

ROBUST_FLAGS=(
    "--force"  # Force operations even if there are minor issues
    "--local-no-check-updated" # Upload file even if it changes during upload (good for logs/trajectories)
    "--create-empty-src-dirs"  # Ensure empty directories are created
    "--retries" "3"  # Retry failed transfers
    "--retries-sleep" "2s"  # Wait between retries
    "--ignore-errors"  # Continue syncing other files even if one fails
)

RCLONE_EXCLUDE_ARGS=(
    --exclude "#*#"
    --exclude "*.swp"
    --exclude "*.tmp"
    --exclude ".nfs*"
    --exclude ".ipynb_checkpoints/**"
    --exclude "**/.ipynb_checkpoints/**"
    --exclude "__pycache__/**"
    --exclude "**/__pycache__/**"
    --exclude ".cache/**"
    --exclude "**/.cache/**"
)

log() {
    echo "$(date): [S3-SETUP] $1" >> "$LOG_DIR/s3-setup.log"
    echo "$(date): [S3-SETUP] $1"
}

setup_s3() {
    if [ -z "$S3_BUCKET" ]; then
        log "No S3 configuration found, using local /mddash"
        mkdir -p /mddash
        return 0
    fi

    log "Setting up S3 bucket ${S3_BUCKET} as /mddash"

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

    log "Setting up S3 access via rclone sync (no FUSE required)"

    # Ensure S3 bucket exists
    log "Creating S3 bucket if it doesn't exist"
    rclone mkdir s3remote:${S3_BUCKET} 2>>"$LOG_DIR/rclone-setup.log" || log "Bucket creation failed or already exists"

    # Initial sync from S3 to local directory
    log "Initial sync from S3 to /mddash"  
    rclone sync s3remote:${S3_BUCKET} /mddash --create-empty-src-dirs --log-level INFO --log-file "$LOG_DIR/rclone-sync.log" "${RCLONE_EXCLUDE_ARGS[@]}"

    # Create marker file if it doesn't exist to enable bisync
    if [ ! -f "/mddash/.s3-init" ]; then
        log "Creating S3 sync marker file"
        echo "There needs to be at least one file in this directory in order for S3 sync to work." > /mddash/.s3-init
        rclone copy /mddash/.s3-init s3remote:${S3_BUCKET}/ --log-level ERROR
    fi

    # Verify sync completed and directory is ready
    if [ -d "/mddash" ]; then
        log "S3 sync setup complete, /mddash is ready"
        ls -la /mddash/ >> "$LOG_DIR/s3-setup.log" 2>&1 || log "Directory exists but may be empty (new bucket)"
    else
        log "ERROR - Failed to set up /mddash directory"
        mkdir -p /mddash
        return 1
    fi

    return 0
}

start_s3_sync_daemon() {
    if [ -z "$S3_BUCKET" ]; then
        return 0
    fi

    log "Starting background S3 sync daemon"
    (
        # Initial resync to ensure consistent state
        log "Performing initial resync..."
        if ! rclone bisync /mddash s3remote:${S3_BUCKET} --resync --log-level INFO \
            "${RCLONE_EXCLUDE_ARGS[@]}" "${ROBUST_FLAGS[@]}" >> "$LOG_DIR/rclone-sync-daemon.log" 2>&1; then
            log "Initial resync failed. Continuing to loop, but state might be inconsistent."
        fi

        FAIL_COUNT=0
        MAX_FAILURES=3

        while true; do
            # Run bisync
            if rclone bisync /mddash s3remote:${S3_BUCKET} --delete-during --log-level ERROR \
                "${RCLONE_EXCLUDE_ARGS[@]}" "${ROBUST_FLAGS[@]}" >> "$LOG_DIR/rclone-sync-daemon.log" 2>&1; then
                
                # Success
                if [ $FAIL_COUNT -gt 0 ]; then
                    log "Sync recovered after $FAIL_COUNT failures."
                fi
                FAIL_COUNT=0
                sleep 10
            else
                EXIT_CODE=$?
                FAIL_COUNT=$((FAIL_COUNT + 1))
                log "Sync failed (Attempt $FAIL_COUNT/$MAX_FAILURES). Exit code: $EXIT_CODE"
                
                # If we have too many failures, try to recover
                if [ $FAIL_COUNT -ge $MAX_FAILURES ]; then
                    log "Critical sync failure detected ($FAIL_COUNT consecutive failures). Attempting recovery with --resync..."
                    
                    # Force resync
                    if rclone bisync /mddash s3remote:${S3_BUCKET} --resync --log-level INFO \
                        "${RCLONE_EXCLUDE_ARGS[@]}" "${ROBUST_FLAGS[@]}" >> "$LOG_DIR/rclone-sync-daemon.log" 2>&1; then
                        log "Recovery successful."
                        FAIL_COUNT=0
                    else
                        log "Recovery failed. Will retry in next cycle."
                        # Backoff longer if recovery fails
                        sleep 60
                    fi
                else
                    # Short backoff for transient errors
                    sleep 10
                fi
            fi
        done
    ) &

    RCLONE_SYNC_PID=$!
    echo "$RCLONE_SYNC_PID" > "$LOG_DIR/rclone-sync.pid"
    log "Background sync started with PID: $RCLONE_SYNC_PID"

    return 0
}

cleanup_s3() {
    if [ -f "$LOG_DIR/rclone-sync.pid" ]; then
        RCLONE_SYNC_PID=$(cat "$LOG_DIR/rclone-sync.pid")
        if [ -n "$RCLONE_SYNC_PID" ]; then
            log "Stopping rclone sync daemon (PID: $RCLONE_SYNC_PID)..."
            kill $RCLONE_SYNC_PID 2>/dev/null || true

            # Final sync before shutdown
            if [ -n "$S3_BUCKET" ]; then
                log "Final sync to S3..."
                rclone sync /mddash s3remote:${S3_BUCKET} --create-empty-src-dirs --force --delete-during \
                    "${RCLONE_EXCLUDE_ARGS[@]}" >> "$LOG_DIR/rclone-final-sync.log" 2>&1 || true
            fi

            rm -f "$LOG_DIR/rclone-sync.pid"
        fi
    fi
}


case "${1:-setup}" in
    "setup")
        setup_s3
        ;;
    "start-daemon")
        start_s3_sync_daemon
        ;;
    "cleanup")
        cleanup_s3
        ;;
    *)
        log "Usage: $0 {setup|start-daemon|cleanup}"
        exit 1
        ;;
esac
