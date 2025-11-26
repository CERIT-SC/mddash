FROM alpine:3.21

RUN apk add --no-cache \
    rclone \
    bash \
    && adduser -D -u 1000 -g 1000 appuser

COPY --chown=1000:1000 ./containers/s3-sync/entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

USER 1000

ENTRYPOINT ["/entrypoint.sh"]
