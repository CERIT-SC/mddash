# API container - Flask backend API service

FROM python:3.12-alpine

WORKDIR /app

RUN addgroup -g 1000 -S app && adduser -u 1000 -S app -G app

RUN apk add --no-cache curl git

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt gunicorn

COPY --chown=app:app . .

RUN mkdir -p /mddash && chown app:app /mddash

USER app

ENV DATA_DIR=/mddash

EXPOSE 5000

HEALTHCHECK --interval=30s --timeout=3s --start-period=10s --retries=3 \
    CMD curl --fail http://localhost:5000/health || exit 1

CMD ["gunicorn", "--bind", "0.0.0.0:5000", "--workers", "1", "--threads", "2", "--access-logfile", "-", "--error-logfile", "-", "app:create_app()"]
