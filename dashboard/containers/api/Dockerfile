FROM python:3.12-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /opt

# Create non-root user
RUN useradd -m -u 1000 appuser && \
    mkdir -p /mddash && \
    chown -R 1000:1000 /opt /mddash

# Install Python dependencies
COPY --chown=1000:1000 ./api/requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir -r /tmp/requirements.txt && rm /tmp/requirements.txt

# Copy API code
COPY --chown=1000:1000 ./api /opt/api
COPY --chown=1000:1000 ./auth /opt/auth
COPY --chown=1000:1000 ./containers/api/entrypoint.sh /entrypoint.sh

RUN chmod +x /entrypoint.sh

USER 1000

EXPOSE 5000 5001

ENTRYPOINT ["/entrypoint.sh"]
