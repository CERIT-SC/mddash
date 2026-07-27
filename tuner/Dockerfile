FROM python:3.13-slim@sha256:6771159cd4fa5d9bba1258caf0b82e6b73458c694d178ad97c5e925c2d0e1a91

COPY --from=ghcr.io/astral-sh/uv:0.11@sha256:df4cae8f3a96d175e2e5f992e597550000edbe78fdc2594d5cd8de1a217f504c /uv /uvx /bin/

WORKDIR /app

RUN groupadd -g 1000 app && useradd -u 1000 -g 1000 -M -s /usr/sbin/nologin app

COPY pyproject.toml uv.lock ./
COPY dashboard/api/pyproject.toml dashboard/api/
COPY dashboard/auth/pyproject.toml dashboard/auth/
COPY mdrun-api/pyproject.toml mdrun-api/
COPY tuner/pyproject.toml tuner/

RUN uv sync --frozen --no-dev --package tuner --no-install-project

COPY --chown=app:app tuner/api/ tuner-runtime/api/
COPY --chown=app:app tuner/migrations/ migrations/
COPY --chown=app:app tuner/alembic.ini .

RUN mkdir -p /data /tmp/tpr && chown app:app /data /tmp/tpr

USER app

ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONPATH="/app/tuner-runtime" \
    RUNTIME_WORKDIR=/app/tuner-runtime \
    PYTHONUNBUFFERED=1

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/api/health').read()" || exit 1

CMD ["python", "tuner-runtime/api/start.py"]
