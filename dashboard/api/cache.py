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

# Cache for tuner job status (30s TTL)
tuner_status_cache: TTLCache = TTLCache(maxsize=100, ttl=30)

# Fallback cache for tuner job failures (job_id -> status)
tuner_last_known_status: dict[str, dict] = {}

# Cache for GROMACS job status (1s TTL)
gromacs_status_cache: TTLCache = TTLCache(maxsize=100, ttl=1)

# Cache for analysis job status (2s TTL — analyses are long-running)
analysis_status_cache: TTLCache = TTLCache(maxsize=100, ttl=2)

# Cache for simulation job status (1s TTL)
simulation_status_cache: TTLCache = TTLCache(maxsize=100, ttl=1)

# Cache for simulation job log line counts (500ms TTL — counting streams whole files)
simulation_log_lines_cache: TTLCache = TTLCache(maxsize=100, ttl=0.5)
