"""
Uvicorn access log filtering.

The uvicorn access logger emits one record per request as
``logger.info(fmt, (client_addr, method, full_path, http_version, status_code))``;
``AccessFormatter.formatMessage`` unpacks that 5-tuple from ``record.args``.
"""

import logging


class HealthCheckFilter(logging.Filter):
    """Suppress successful health-check access logs."""

    def filter(self, record: logging.LogRecord) -> bool:
        """Return False to drop successful health probes; keep all else."""
        args = record.args
        if not isinstance(args, tuple):
            return True
        try:
            path = str(args[2]).rstrip("/")
            status = str(args[4])
        except IndexError:
            return True
        return not (path.endswith("/health") and status == "200")
