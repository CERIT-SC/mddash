FROM python:3.11-slim AS builder

WORKDIR /app

RUN apt-get update && apt-get install -y \
    gcc \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt


FROM python:3.11-slim AS production

WORKDIR /app

COPY --from=builder /usr/local/lib/python3.11/site-packages /usr/local/lib/python3.11/site-packages
COPY --from=builder /usr/local/bin /usr/local/bin

COPY . .

RUN mkdir -p /data && \
    addgroup --gid 1000 appgroup && \
    adduser --uid 1000 --gid 1000 --disabled-password --gecos "" appuser && \
    chown -R appuser:appgroup /data /app

USER appuser

EXPOSE 5000

ENV APP_ENV=prod
ENV UWSGI_PROCESSES=4
ENV UWSGI_THREADS=2
ENV UWSGI_ENABLE_THREADS=1

# basically a curl, but using python to avoid extra dependencies
HEALTHCHECK --interval=30s --timeout=3s --start-period=5s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:5000/health').read()" || exit 1

CMD ["sh", "-c", "uwsgi --http 0.0.0.0:5000 --module app:app --processes $UWSGI_PROCESSES --threads $UWSGI_THREADS --enable-threads --master --die-on-term 2>&1 | tee /data/api.log"]
