FROM python:3.12-slim

COPY --from=ghcr.io/astral-sh/uv:0.11 /uv /uvx /bin/

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml uv.lock ./
COPY dashboard/api/pyproject.toml dashboard/api/
COPY dashboard/auth/pyproject.toml dashboard/auth/
COPY mdrun-api/pyproject.toml mdrun-api/
COPY notebook/pyproject.toml notebook/

RUN uv sync --frozen --no-dev --extra prod --package mdrun-api --no-install-project

COPY mdrun-api/ .

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
ENV PATH="/app/.venv/bin:$PATH"

HEALTHCHECK --interval=30s --timeout=3s --start-period=5s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:5000/api/health').read()" || exit 1

CMD ["sh", "-c", "uwsgi --http 0.0.0.0:5000 --module app:app --processes $UWSGI_PROCESSES --threads $UWSGI_THREADS --enable-threads --master --die-on-term 2>&1 | tee /data/api.log"]
