# MDRun API

Flask-based API for managing molecular dynamics simulation jobs.

## Development mode

- Uses Flask's built-in development server with hot-reload
- Debug mode enabled
- SQL query logging enabled
- Detailed logging (DEBUG level)

**Build and run.**
```bash
make build-dev
docker run -p 5000:5000 -v $(pwd):/app <image>:dev
```

## Production mode

- Gunicorn with 2 workers and 4 threads by default
- Health check endpoint configured
- INFO level logging

**Build and run.**
```bash
make build-prod
docker push <image>:latest
```

## Environment variables

- `APP_ENV`: Set to `dev` or `prod` (default: `prod`)
- `GUNICORN_WORKERS`: Number of Gunicorn worker processes (default: 2)
- `GUNICORN_THREADS`: Number of threads per worker (default: 4)
- `POD_NAMESPACE`: Kubernetes namespace (default: `default`)
- `PVC_NAME`: Persistent volume claim name (default: `mdrun-api-pvc`)
- `S3_CREDENTIALS`: S3 access credentials
- `S3_ENDPOINT`: S3 endpoint URL
