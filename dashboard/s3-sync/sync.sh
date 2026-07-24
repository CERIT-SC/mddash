#!/bin/sh
set -euo pipefail

log() { echo "$(date '+%Y-%m-%d %H:%M:%S') [S3-SYNC] $1"; }

WORKDIR="/mddash/.rclone-bisync"
FILTERS_FILE="$WORKDIR/filters.txt"
SRC_FILTERS="/rclone-filters.txt"

# No --create-empty-src-dirs: S3 can't hold empty dirs, so the flag makes bisync delete them from the PVC next cycle.
# --force: bypass --max-delete; user-initiated deletes (incl. rm -rf) propagate as on a normal filesystem.
COMMON_FLAGS="--workdir $WORKDIR \
  --force --ignore-errors --fast-list --local-no-check-updated \
  --filter-from $FILTERS_FILE"

RUN_FLAGS="--recover --resilient --max-lock 2m --conflict-resolve newer --retries 3 --retries-sleep 2s"

# --max-lock is required on resync: a lock's expiry is set by the creating
# process, so an interrupted resync without --max-lock leaves a never-expiring
# .lck that blocks all future runs (the normal loop's --max-lock can't break a
# lock it did not create).
RESYNC_FLAGS="--resync --resync-mode newer $COMMON_FLAGS --max-lock 2m --resilient --log-level INFO"

setup_rclone() {
    [ -n "$S3_BUCKET" ] || { log "No S3_BUCKET configured, local-only mode"; exit 0; }

    log "Configuring rclone for bucket: $S3_BUCKET"
    mkdir -p "$HOME/.config/rclone"
    cat > "$HOME/.config/rclone/rclone.conf" << EOF
[s3remote]
type = s3
provider = Other
access_key_id = ${S3_ACCESS_KEY}
secret_access_key = ${S3_SECRET_KEY}
endpoint = ${S3_ENDPOINT}
EOF

    log "Creating bucket if it doesn't exist..."
    rclone mkdir s3remote:${S3_BUCKET} 2>&1 || log "Bucket creation failed or already exists"

    # Non-excluded marker: keeps both paths non-empty so bisync's empty-path
    # safety check doesn't abort every cycle on a fresh PVC.
    if [ ! -f "/mddash/.s3-init" ]; then
        log "Creating S3 sync marker file"
        echo "S3 sync marker - do not delete" > /mddash/.s3-init
    fi
    rclone copyto /mddash/.s3-init s3remote:${S3_BUCKET}/.s3-init --log-level ERROR \
        || log "Marker copy to S3 failed, continuing"

    # Stage filters into the workdir: bisync writes its filter-hash .md5 next to them.
    mkdir -p "$WORKDIR"
    cp "$SRC_FILTERS" "$FILTERS_FILE"
}

is_first_run() {
    ! ls "$WORKDIR"/*.lst >/dev/null 2>&1 && ! ls "$WORKDIR"/*.lst-err >/dev/null 2>&1
}

initial_sync() {
    if is_first_run; then
        log "First run (no state in $WORKDIR): initial --resync (--resync-mode newer)..."
        rclone bisync /mddash s3remote:${S3_BUCKET} $RESYNC_FLAGS \
            || log "Initial resync had issues, will retry in loop"
    else
        log "Prior state found in $WORKDIR, skipping resync"
    fi
}

run_sync_loop() {
    [ -n "$S3_BUCKET" ] || { log "No S3_BUCKET configured, sleeping indefinitely"; sleep infinity; }

    log "Starting sync loop..."
    initial_sync

    FAIL_COUNT=0
    MAX_FAILS=6

    while true; do
        if is_first_run; then
            # Retry as --resync (not stateless bisync) when no .lst state exists,
            # e.g. if initial_sync's resync failed without writing state.
            log "No bisync state yet, retrying --resync..."
            if rclone bisync /mddash s3remote:${S3_BUCKET} $RESYNC_FLAGS 2>&1; then
                FAIL_COUNT=0
            else
                FAIL_COUNT=$((FAIL_COUNT + 1))
                log "Resync failed ($FAIL_COUNT), backing off"
                sleep $((FAIL_COUNT * 10))
                continue
            fi
        elif rclone bisync /mddash s3remote:${S3_BUCKET} \
            $RUN_FLAGS $COMMON_FLAGS --log-level ERROR 2>&1; then
            [ "$FAIL_COUNT" -gt 0 ] && log "Sync recovered after $FAIL_COUNT failures"
            FAIL_COUNT=0
        else
            EXIT_CODE=$?
            FAIL_COUNT=$((FAIL_COUNT + 1))
            # .lst-err is a critical lockout: only --resync recovers it.
            if ls "$WORKDIR"/*.lst-err >/dev/null 2>&1; then
                log "Critical lockout (.lst-err): running recovery --resync..."
                if rclone bisync /mddash s3remote:${S3_BUCKET} $RESYNC_FLAGS 2>&1; then
                    log "Recovery resync successful"; FAIL_COUNT=0
                else
                    log "Recovery resync failed, backing off 60s"; sleep 60; continue
                fi
            elif [ "$FAIL_COUNT" -ge "$MAX_FAILS" ]; then
                log "Persistent failure ($FAIL_COUNT): fallback --resync..."
                if rclone bisync /mddash s3remote:${S3_BUCKET} $RESYNC_FLAGS 2>&1; then
                    log "Fallback resync successful"; FAIL_COUNT=0
                else
                    log "Fallback resync failed, backing off 60s"; sleep 60; continue
                fi
            else
                # Do NOT resync here: it only copies and would re-create deleted files/dirs.
                log "Transient failure ($FAIL_COUNT/$MAX_FAILS, exit $EXIT_CODE), backing off"
                sleep $((FAIL_COUNT * 10))
                continue
            fi
        fi
        sleep 10
    done
}

final_sync() {
    [ -n "$S3_BUCKET" ] || return 0
    # Non-destructive: never use `rclone sync --delete-during` here, it would
    # delete remote files if the PVC were only partially populated.
    log "Performing final bisync to S3..."
    rclone bisync /mddash s3remote:${S3_BUCKET} \
        $RUN_FLAGS $COMMON_FLAGS --log-level INFO 2>&1 || log "Final sync had issues"
    log "Final sync complete"
}

trap 'final_sync; exit 0' TERM INT

setup_rclone
run_sync_loop
