"""
Shared TTL caches for upstream state, keyed by stable ids.

The async refresh step reads and writes them on the event loop; only
`simulation_log_lines_cache` is touched from serialization worker threads,
hence its lock.
"""

import threading

from cachetools import TTLCache

# MDRepo publication status keyed by record id (60s TTL)
mdrepo_status_cache: TTLCache = TTLCache(maxsize=100, ttl=60)

# Coalesce tuner status requests for 1s; UI polls every 5s
tuner_status_cache: TTLCache = TTLCache(maxsize=100, ttl=1)

# Fallback for tuner job failures (job_id -> status)
tuner_last_known_status: dict[str, dict] = {}

# Analysis job status keyed by job id; analyses run for a long time (2s TTL)
analysis_status_cache: TTLCache = TTLCache(maxsize=100, ttl=2)

# MDRun job status keyed by job id (1s TTL)
simulation_status_cache: TTLCache = TTLCache(maxsize=100, ttl=1)

# Log line counts keyed by job id live 30s; counting streams whole files
simulation_log_lines_cache: TTLCache = TTLCache(maxsize=100, ttl=30)
simulation_log_lines_lock = threading.Lock()

# Archive/restore Job liveness keyed by (direction, experiment_id)
# (1s TTL for request coalescing only; archive lists serialize every experiment)
archive_status_cache: TTLCache = TTLCache(maxsize=500, ttl=1)
