# S3 Sync container - bidirectional sync between /mddash volume and S3

FROM alpine:3.20

RUN apk add --no-cache rclone

RUN addgroup -S app && adduser -S app -G app

COPY --chown=app:app sync.sh /sync.sh
RUN chmod +x /sync.sh

USER app

CMD ["/sync.sh"]
