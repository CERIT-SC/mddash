FROM node:24-slim AS build-stage
WORKDIR /usr/src/app

COPY ./dash/package*.json ./
RUN npm install --force

COPY ./dash .
RUN npm run build

FROM caddy:2.10-alpine AS caddy-stage

# remove cap_net_bind_service because caddy will not be binding privileged ports
RUN apk add --no-cache libcap && setcap -r /usr/bin/caddy

FROM quay.io/jupyterhub/singleuser:5

USER root

# Install rclone for mounting S3 buckets and util-linux for mountpoint command
RUN apt-get update && apt-get install -y curl unzip util-linux && \
    curl -O https://downloads.rclone.org/rclone-current-linux-amd64.zip && \
    unzip rclone-current-linux-amd64.zip && \
    cp rclone-*/rclone /usr/bin/ && \
    chmod 755 /usr/bin/rclone && \
    rm -rf rclone-* && \
    apt-get clean && rm -rf /var/lib/apt/lists/*

# api requirements
COPY ./api/requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir -r /tmp/requirements.txt && rm /tmp/requirements.txt

RUN mkdir -p /mddash/logs /caddy/data /caddy/config

COPY --from=caddy-stage --chown=1000:100 /usr/bin/caddy /usr/bin/caddy
COPY --from=build-stage --chown=1000:100 /usr/src/app/dist /opt/dash
COPY --chown=1000:100 ./api /opt/api
COPY --chown=1000:100 ./Caddyfile /caddy/
COPY --chown=1000:100 ./entrypoint.sh /entrypoint.sh

RUN chown -R 1000:100 /mddash /caddy && \
    chmod +x /entrypoint.sh

ENV XDG_DATA_HOME=/caddy/data
ENV XDG_CONFIG_HOME=/caddy/config

USER 1000

EXPOSE 8888

ENTRYPOINT ["/entrypoint.sh"]
