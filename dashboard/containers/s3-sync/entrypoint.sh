#!/bin/bash
set -euo pipefail

LOG_DIR="/tmp/mddash-logs"
mkdir -p "$LOG_DIR"

ROBUST_FLAGS=(
    "--force"
    "--local-no-check-updated"
    "--create-empty-src-dirs"
    "--retries" "3"
    "--retries-sleep" "2s"
    "--ignore-errors"
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
    echo "$(date): [S3-SYNC] $1"
}

setup_rclone() {
    if [ -z "${S3_BUCKET:-}" ]; then
        log "No S3 configuration found, exiting"
        exit 0
    fi

    log "Setting up rclone for S3 bucket ${S3_BUCKET}"

    mkdir -p ~/.config/rclone
    cat > ~/.config/rclone/rclone.conf << EOF
[s3remote]
type = s3
provider = Other
access_key_id = ${S3_ACCESS_KEY}
secret_access_key = ${S3_SECRET_KEY}
endpoint = ${S3_ENDPOINT}
EOF

    mkdir -p /mddash
}

initial_sync() {
    log "Creating S3 bucket if it doesn't exist"
    rclone mkdir "s3remote:${S3_BUCKET}" 2>/dev/null || log "Bucket creation failed or already exists"

    log "Initial sync from S3 to /mddash"
    rclone sync "s3remote:${S3_BUCKET}" /mddash --create-empty-src-dirs --log-level INFO "${RCLONE_EXCLUDE_ARGS[@]}"

    if [ ! -f "/mddash/.s3-init" ]; then
        log "Creating S3 sync marker file"
        echo "There needs to be at least one file in this directory in order for S3 sync to work." > /mddash/.s3-init
        rclone copy /mddash/.s3-init "s3remote:${S3_BUCKET}/" --log-level ERROR
    fi

    log "S3 initial sync complete, /mddash is ready"
}

resync() {
    log "Performing initial resync..."
    if ! rclone bisync /mddash "s3remote:${S3_BUCKET}" --resync --log-level INFO \
        "${RCLONE_EXCLUDE_ARGS[@]}" "${ROBUST_FLAGS[@]}"; then
        log "Initial resync failed. Continuing to loop, but state might be inconsistent."
    fi
}

sync_loop() {
    FAIL_COUNT=0
    MAX_FAILURES=3

    while true; do
        if rclone bisync /mddash "s3remote:${S3_BUCKET}" --delete-during --log-level ERROR \
            "${RCLONE_EXCLUDE_ARGS[@]}" "${ROBUST_FLAGS[@]}"; then

            if [ $FAIL_COUNT -gt 0 ]; then
                log "Sync recovered after $FAIL_COUNT failures."
            fi
            FAIL_COUNT=0
            sleep 10
        else
            EXIT_CODE=$?
            FAIL_COUNT=$((FAIL_COUNT + 1))
            log "Sync failed (Attempt $FAIL_COUNT/$MAX_FAILURES). Exit code: $EXIT_CODE"

            if [ $FAIL_COUNT -ge $MAX_FAILURES ]; then
                log "Critical sync failure detected ($FAIL_COUNT consecutive failures). Attempting recovery with --resync..."

                if rclone bisync /mddash "s3remote:${S3_BUCKET}" --resync --log-level INFO \
                    "${RCLONE_EXCLUDE_ARGS[@]}" "${ROBUST_FLAGS[@]}"; then
                    log "Recovery successful."
                    FAIL_COUNT=0
                else
                    log "Recovery failed. Will retry in next cycle."
                    sleep 60
                fi
            else
                sleep 10
            fi
        fi
    done
}

cleanup() {
    log "Received shutdown signal, performing final sync..."
    if [ -n "${S3_BUCKET:-}" ]; then
        rclone sync /mddash "s3remote:${S3_BUCKET}" --create-empty-src-dirs --force --delete-during \
            "${RCLONE_EXCLUDE_ARGS[@]}" 2>/dev/null || true
    fi
    log "Final sync complete, exiting"
    exit 0
}

trap cleanup SIGTERM SIGINT

log "Starting S3 sync container..."
setup_rclone
initial_sync
resync
sync_loop
