FROM python:3.11-slim

WORKDIR /app

# Copy requirements first for better Docker layer caching
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Create data directory
RUN mkdir -p /data

# Expose port
EXPOSE 5000

# Default values for uWSGI
ENV UWSGI_PROCESSES=4
ENV UWSGI_THREADS=2

# Run with uWSGI using environment variables and log to /data/api.log
CMD ["sh", "-c", "uwsgi --http 0.0.0.0:5000 --module app:app --processes $UWSGI_PROCESSES --threads $UWSGI_THREADS > /data/api.log 2>&1"]
