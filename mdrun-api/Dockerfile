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

# Run with uWSGI
CMD ["uwsgi", "--http", "0.0.0.0:5000", "--module", "app:app", "--processes", "4", "--threads", "2"]
