FROM rclone/rclone:1.74.4 AS rclone

FROM python:3.12-alpine

COPY --from=rclone /usr/local/bin/rclone /usr/bin/rclone
RUN apk add --no-cache ca-certificates
RUN pip install --no-cache-dir requests

RUN addgroup -g 1000 -S app && adduser -u 1000 -S app -G app
ENV HOME=/home/app

COPY --chown=app:app mdrepo-uploader/worker.py rclone-filters.txt /
RUN chmod +x /worker.py

USER app
CMD ["python", "/worker.py"]
