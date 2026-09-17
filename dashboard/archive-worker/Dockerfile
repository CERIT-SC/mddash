FROM rclone/rclone:1.74.4

# Reuses the s3-sync filter file so "archive-worthy" always means "what bisync syncs".
COPY archive-worker/worker.sh s3-sync/rclone-filters.txt /
RUN chmod 755 /worker.sh

ENTRYPOINT ["sh", "/worker.sh"]
