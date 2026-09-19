FROM rclone/rclone:1.74.4

# Bakes the shared filter list so "archive-worthy" always means "what bisync syncs".
COPY --chmod=755 archive-worker/worker.sh /
COPY rclone-filters.txt /

ENTRYPOINT ["sh", "/worker.sh"]
