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

# Cache for metrics (pod resources and directory size) (120s TTL)
metrics_cache: TTLCache = TTLCache(maxsize=2, ttl=120)

# Cache for tuner job status (30s TTL)
tuner_status_cache: TTLCache = TTLCache(maxsize=100, ttl=30)

# Fallback cache for tuner job failures (job_id -> status)
tuner_last_known_status: dict[str, dict] = {}

# Cache for GROMACS job status (1s TTL)
gromacs_status_cache: TTLCache = TTLCache(maxsize=100, ttl=1)

# Cache for GROMACS job performance metrics (1s TTL)
gromacs_performance_cache: TTLCache = TTLCache(maxsize=100, ttl=1)

# Cache for GROMACS job nsteps done (500ms TTL)
gromacs_nsteps_done_cache: TTLCache = TTLCache(maxsize=100, ttl=0.5)

# Cache for GROMACS job estimated time (500ms TTL)
gromacs_estimated_time_cache: TTLCache = TTLCache(maxsize=100, ttl=0.5)
