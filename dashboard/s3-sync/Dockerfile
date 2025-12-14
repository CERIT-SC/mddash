# S3 Sync container - bidirectional sync between /mddash volume and S3

FROM alpine:3.20

RUN apk add --no-cache rclone curl

RUN addgroup -g 1000 -S app && adduser -u 1000 -S app -G app

ENV HOME=/home/app

COPY --chown=app:app sync.sh rclone-filters.txt /
RUN chmod +x /sync.sh

USER app

CMD ["/sync.sh"]
