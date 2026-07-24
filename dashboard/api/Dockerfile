# API container - Flask backend API service

FROM python:3.13-slim

COPY --from=ghcr.io/astral-sh/uv:0.11 /uv /uvx /bin/

WORKDIR /app

RUN groupadd -g 1000 app && useradd -u 1000 -g 1000 -M -s /usr/sbin/nologin app

RUN apt-get update \
    && apt-get install -y --no-install-recommends curl git \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml uv.lock ./
COPY dashboard/api/pyproject.toml dashboard/api/
COPY dashboard/auth/pyproject.toml dashboard/auth/
COPY mdrun-api/pyproject.toml mdrun-api/

RUN uv sync --frozen --no-dev --package dashboard-api --no-install-project

COPY --chown=app:app dashboard/api/ .

RUN mkdir -p /mddash && chown app:app /mddash
RUN mkdir -p /home/app && chown app:app /home/app

USER app

ENV DATA_DIR=/mddash
ENV HOME=/home/app
ENV PATH="/app/.venv/bin:$PATH"

EXPOSE 5000

HEALTHCHECK --interval=30s --timeout=3s --start-period=10s --retries=3 \
    CMD curl --fail http://localhost:5000/health || exit 1

CMD ["gunicorn", "--bind", "0.0.0.0:5000", "--workers", "1", "--threads", "2", "--access-logfile", "-", "--error-logfile", "-", "app:create_app()"]
