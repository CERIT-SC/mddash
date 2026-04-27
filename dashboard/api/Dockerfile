# API container - Flask backend API service

FROM python:3.12-slim

COPY --from=ghcr.io/astral-sh/uv:0.5 /uv /uvx /bin/

WORKDIR /app

RUN groupadd -g 1000 app && useradd -u 1000 -g 1000 -M -s /usr/sbin/nologin app

RUN apt-get update \
    && apt-get install -y --no-install-recommends curl git \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

COPY --chown=app:app . .

RUN mkdir -p /mddash && chown app:app /mddash

USER app

ENV DATA_DIR=/mddash
ENV PATH="/app/.venv/bin:$PATH"

EXPOSE 5000

HEALTHCHECK --interval=30s --timeout=3s --start-period=10s --retries=3 \
    CMD curl --fail http://localhost:5000/health || exit 1

CMD ["gunicorn", "--bind", "0.0.0.0:5000", "--workers", "1", "--threads", "2", "--access-logfile", "-", "--error-logfile", "-", "app:create_app()"]
