#!/bin/sh
# Mirror one experiment between the PVC (/mddash/<id>) and the bisync-excluded S3 prefix _archives/<id>/.
# Usage: worker.sh <archive|restore|purge> --experiment-id <id> --attempt-id <hex>
# Status failures use fixed reason tokens: rclone stderr may carry credentials and stays in Job logs.
set -eu

DATA_DIR=${DATA_DIR:-/mddash}
FILTERS=${FILTERS_FILE:-/rclone-filters.txt}
RCLONE_CONFIG=${RCLONE_CONFIG:-/tmp/rclone/rclone.conf}
REMOTE="s3remote"

log() { echo "$(date '+%Y-%m-%d %H:%M:%S') [ARCHIVE-WORKER] $1"; }

usage() {
    echo "Usage: worker.sh <archive|restore|purge> --experiment-id <id> --attempt-id <hex>" >&2
    exit 2
}

MODE="${1:-}"
[ "$MODE" = "archive" ] || [ "$MODE" = "restore" ] || [ "$MODE" = "purge" ] || usage
shift

EXPERIMENT_ID=""
ATTEMPT_ID=""
while [ $# -gt 0 ]; do
    case "$1" in
        --experiment-id) EXPERIMENT_ID="$2"; shift 2 ;;
        --attempt-id) ATTEMPT_ID="$2"; shift 2 ;;
        *) usage ;;
    esac
done
[ -n "$EXPERIMENT_ID" ] && [ -n "$ATTEMPT_ID" ] || usage

for var in S3_BUCKET S3_ENDPOINT S3_ACCESS_KEY S3_SECRET_KEY; do
    eval "value=\${$var:-}"
    [ -n "$value" ] || { log "Missing required env: $var"; exit 2; }
done

EXP_DIR="$DATA_DIR/$EXPERIMENT_ID"
STATUS_PATH="$EXP_DIR/.archive-status.json"
ARCHIVE_PREFIX="$REMOTE:$S3_BUCKET/_archives/$EXPERIMENT_ID"
LIVE_PREFIX="$REMOTE:$S3_BUCKET/$EXPERIMENT_ID"
RCLONE="rclone --config $RCLONE_CONFIG"

setup_rclone() {
    mkdir -p "$(dirname "$RCLONE_CONFIG")"
    cat > "$RCLONE_CONFIG" << EOF
[$REMOTE]
type = s3
provider = Other
access_key_id = ${S3_ACCESS_KEY}
secret_access_key = ${S3_SECRET_KEY}
endpoint = ${S3_ENDPOINT}
EOF
}

# Atomic status write (tmp + rename); fields are fixed tokens, never rclone stderr.
write_status() {
    state="$1"
    reason="${2:-}"
    tmp="$STATUS_PATH.tmp"
    mkdir -p "$(dirname "$tmp")"
    if [ -n "$reason" ]; then
        printf '%s\n' "{\"attempt_id\": \"$ATTEMPT_ID\", \"state\": \"$state\", \"direction\": \"$MODE\", \"reason\": \"$reason\"}" > "$tmp"
    else
        printf '%s\n' "{\"attempt_id\": \"$ATTEMPT_ID\", \"state\": \"$state\", \"direction\": \"$MODE\", \"reason\": null}" > "$tmp"
    fi
    mv "$tmp" "$STATUS_PATH"
}

fail() {
    reason="$1"
    log "FAILED ($reason)"
    [ "$MODE" = "purge" ] || write_status failed "$reason"
    exit 1
}

# No status write on refusal: a failed doc here would read as our retry
# sentinel and unlock clobbering foreign data on the next attempt.
reject() {
    reason="$1"
    log "REFUSED ($reason)"
    exit 1
}

run_archive() {
    [ -d "$EXP_DIR" ] || fail "source-missing"

    write_status running

    # Server-side seed; an absent live prefix is fine.
    log "Server-side copy $LIVE_PREFIX -> $ARCHIVE_PREFIX"
    $RCLONE copy "$LIVE_PREFIX" "$ARCHIVE_PREFIX" --filter-from "$FILTERS" || fail "seed-copy"

    # sync, not copy: stale objects from an earlier archive/restore cycle must
    # be deleted for re-archive to pass the symmetric check.
    log "Syncing top-up from $EXP_DIR"
    $RCLONE sync "$EXP_DIR" "$ARCHIVE_PREFIX" --filter-from "$FILTERS" || fail "delta-sync"

    # size-only: multipart ETags are not MD5s.
    log "Verifying archive against PVC"
    $RCLONE check "$ARCHIVE_PREFIX" "$EXP_DIR" --filter-from "$FILTERS" --size-only || fail "check"

    write_status completed
    log "Archive verified; deleting $EXP_DIR"
    rm -rf "$EXP_DIR" || { log "WARNING: local cleanup of $EXP_DIR failed"; exit 1; }
    log "Archive complete"
}

run_restore() {
    if [ -e "$EXP_DIR" ]; then
        # The API never writes restore docs, so any doc here is a previous attempt's:
        # non-completed marks a resumable leftover, anything else is clobber protection.
        if [ ! -f "$STATUS_PATH" ] \
            || ! grep -q '"direction": *"restore"' "$STATUS_PATH" \
            || grep -q '"state": *"completed"' "$STATUS_PATH"; then
            reject "target-exists"
        fi
        log "Continuing incomplete restore (retry sentinel found)"
    fi

    if [ -z "$($RCLONE lsf "$ARCHIVE_PREFIX" 2>/dev/null)" ]; then
        fail "archive-empty"
    fi

    write_status running

    # Filtered so the local status doc can't read as a dest-side extra in check.
    log "Copying $ARCHIVE_PREFIX -> $EXP_DIR"
    $RCLONE copy "$ARCHIVE_PREFIX" "$EXP_DIR" --filter-from "$FILTERS" || fail "copy"

    log "Verifying restore"
    $RCLONE check "$ARCHIVE_PREFIX" "$EXP_DIR" --filter-from "$FILTERS" --size-only || fail "check"

    write_status completed
    log "Restore complete"
}

run_purge() {
    log "Purging $ARCHIVE_PREFIX"
    $RCLONE purge "$ARCHIVE_PREFIX" || { log "Purge failed"; exit 1; }
    log "Purge complete"
}

setup_rclone
case "$MODE" in
    archive) run_archive ;;
    restore) run_restore ;;
    purge) run_purge ;;
esac
