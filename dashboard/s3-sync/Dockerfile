FROM rclone/rclone:1.74.4 AS rclone

FROM alpine:3.20

COPY --from=rclone /usr/local/bin/rclone /usr/bin/rclone
RUN apk add --no-cache ca-certificates

RUN addgroup -g 1000 -S app && adduser -u 1000 -S app -G app
ENV HOME=/home/app

COPY --chown=app:app sync.sh rclone-filters.txt /
RUN chmod +x /sync.sh

USER app
CMD ["/sync.sh"]
