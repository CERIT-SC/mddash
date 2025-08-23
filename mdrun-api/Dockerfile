FROM python:3.11-slim

WORKDIR /app

# Install build dependencies for uWSGI
RUN apt-get update && apt-get install -y \
    gcc \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

RUN mkdir -p /data
RUN chown -R 1000:1000 /data /app

USER 1000:1000

EXPOSE 5000

ENV UWSGI_PROCESSES=4
ENV UWSGI_THREADS=2

CMD ["sh", "-c", "uwsgi --http 0.0.0.0:5000 --module app:app --processes $UWSGI_PROCESSES --threads $UWSGI_THREADS > /data/api.log 2>&1"]
