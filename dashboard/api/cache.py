"""
Shared cache instances for the Dashboard API.

This module provides centralized cache instances that can be imported
by multiple modules without creating circular dependencies.
"""

from cachetools import TTLCache

# Cache for experiment step status (100ms TTL)
step_status_cache: TTLCache = TTLCache(maxsize=100, ttl=0.1)

# Cache for MDRepo publication status (60s TTL)
mdrepo_status_cache: TTLCache = TTLCache(maxsize=100, ttl=60)

# Coalesce tuner status requests for 1s; UI polls every 5s
tuner_status_cache: TTLCache = TTLCache(maxsize=100, ttl=1)

# Fallback cache for tuner job failures (job_id -> status)
tuner_last_known_status: dict[str, dict] = {}

# Cache for GROMACS job status (1s TTL)
gromacs_status_cache: TTLCache = TTLCache(maxsize=100, ttl=1)

# Hold analysis status for 2s; analyses run for a long time
analysis_status_cache: TTLCache = TTLCache(maxsize=100, ttl=2)

# Cache for simulation job status (1s TTL)
simulation_status_cache: TTLCache = TTLCache(maxsize=100, ttl=1)

# Log line counts keyed by job id live 30s; counting streams whole files
simulation_log_lines_cache: TTLCache = TTLCache(maxsize=100, ttl=30)

# Cache for archive/restore Job liveness keyed by (direction, experiment_id)
# (1s TTL for request coalescing only; archive lists serialize every experiment)
archive_status_cache: TTLCache = TTLCache(maxsize=500, ttl=1)
