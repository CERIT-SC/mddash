#!/bin/sh
set -euo pipefail

# S3 Sync Container - bidirectional sync between /mddash and S3 bucket

log() {
    echo "$(date '+%Y-%m-%d %H:%M:%S') [S3-SYNC] $1"
}

ROBUST_FLAGS="--force --local-no-check-updated --create-empty-src-dirs --retries 3 --retries-sleep 2s --ignore-errors --fast-list"
RCLONE_FILTER_FILE="/rclone-filters.txt"

setup_rclone() {
    if [ -z "$S3_BUCKET" ]; then
        log "No S3_BUCKET configured, running in local-only mode"
        exit 0
    fi

    log "Configuring rclone for bucket: $S3_BUCKET"
    
    mkdir -p ~/.config/rclone
    cat > ~/.config/rclone/rclone.conf << EOF
[s3remote]
type = s3
provider = Other
access_key_id = ${S3_ACCESS_KEY}
secret_access_key = ${S3_SECRET_KEY}
endpoint = ${S3_ENDPOINT}
EOF

    # Ensure bucket exists
    log "Creating bucket if it doesn't exist..."
    rclone mkdir s3remote:${S3_BUCKET} 2>&1 || log "Bucket creation failed or already exists"

    # Initial sync from S3 - use copy + update instead of sync
    # This avoids deleting local files and only overwrites if S3 has a newer version
    log "Initial sync from S3 to /mddash..."
    rclone copy s3remote:${S3_BUCKET} /mddash --create-empty-src-dirs --log-level INFO --filter-from "$RCLONE_FILTER_FILE" --update --fast-list

    # Create marker file for bisync
    if [ ! -f "/mddash/.s3-init" ]; then
        log "Creating S3 sync marker file"
        echo "S3 sync marker - do not delete" > /mddash/.s3-init
        rclone copy /mddash/.s3-init s3remote:${S3_BUCKET}/ --log-level ERROR
    fi

    log "Initial setup complete"
}

run_sync_loop() {
    if [ -z "$S3_BUCKET" ]; then
        log "No S3_BUCKET configured, sleeping indefinitely"
        sleep infinity
    fi

    log "Starting sync loop..."
    
    # Initial resync to establish baseline
    log "Performing initial bisync resync..."
    rclone bisync /mddash s3remote:${S3_BUCKET} --resync --log-level INFO --filter-from "$RCLONE_FILTER_FILE" $ROBUST_FLAGS || log "Initial resync had issues, continuing..."

    FAIL_COUNT=0
    MAX_FAILURES=3

    while true; do
        if rclone bisync /mddash s3remote:${S3_BUCKET} --delete-during --log-level ERROR --filter-from "$RCLONE_FILTER_FILE" $ROBUST_FLAGS 2>&1; then
            if [ $FAIL_COUNT -gt 0 ]; then
                log "Sync recovered after $FAIL_COUNT failures"
            fi
            FAIL_COUNT=0
        else
            EXIT_CODE=$?
            FAIL_COUNT=$((FAIL_COUNT + 1))
            log "Sync failed (attempt $FAIL_COUNT/$MAX_FAILURES), exit code: $EXIT_CODE"
            
            if [ $FAIL_COUNT -ge $MAX_FAILURES ]; then
                log "Critical failure, attempting recovery with --resync..."
                if rclone bisync /mddash s3remote:${S3_BUCKET} --resync --log-level INFO --filter-from "$RCLONE_FILTER_FILE" $ROBUST_FLAGS 2>&1; then
                    log "Recovery successful"
                    FAIL_COUNT=0
                else
                    log "Recovery failed, will retry after longer delay"
                    sleep 60
                    continue
                fi
            fi
        fi
        sleep 10
    done
}

final_sync() {
    if [ -z "$S3_BUCKET" ]; then
        return 0
    fi
    
    log "Performing final sync to S3..."
    rclone sync /mddash s3remote:${S3_BUCKET} --create-empty-src-dirs --force --delete-during --filter-from "$RCLONE_FILTER_FILE" 2>&1 || log "Final sync had issues"
    log "Final sync complete"
}

# Handle shutdown gracefully
trap 'final_sync; exit 0' TERM INT

# Main execution
setup_rclone
run_sync_loop
