# Auth container - OAuth forward authentication service for Caddy

FROM python:3.13-alpine

COPY --from=ghcr.io/astral-sh/uv:0.11 /uv /uvx /bin/

WORKDIR /app

RUN addgroup -g 1000 -S app && adduser -u 1000 -S app -G app

COPY pyproject.toml uv.lock ./
COPY dashboard/api/pyproject.toml dashboard/api/
COPY dashboard/auth/pyproject.toml dashboard/auth/
COPY mdrun-api/pyproject.toml mdrun-api/
COPY tuner/pyproject.toml tuner/

RUN uv sync --frozen --no-dev --package dashboard-auth --no-install-project

COPY --chown=app:app dashboard/auth/ ./

USER app

ENV PATH="/app/.venv/bin:$PATH"

EXPOSE 5001

HEALTHCHECK --interval=30s --timeout=3s --start-period=5s --retries=3 \
    CMD wget --spider --quiet http://localhost:5001/health || exit 1

CMD ["gunicorn", "--bind", "0.0.0.0:5001", "--workers", "1", "--access-logfile", "-", "--error-logfile", "-", "--logger-class", "gunicorn_logging.HealthCheckFilter", "auth:app"]
