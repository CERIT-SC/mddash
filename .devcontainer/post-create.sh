#!/bin/bash
set -euo pipefail

# Sync workspace venv for IDE type resolution
uv sync --all-packages --group dev

# Sync per-component Python environments
(cd dashboard/api && uv sync --group dev)
(cd dashboard/auth && uv sync --group dev)
# mdrun-api requires uwsgi (C extension) — skip it in devcontainer, Docker build compiles it
(cd mdrun-api && uv sync --group dev --no-install-project 2>/dev/null || \
  echo "⚠️  mdrun-api: some packages skipped (build tools unavailable). Docker build handles them.")

# Install extra deps used in helm/pre_spawn_hook.py into the api venv
(cd dashboard/api && uv pip install aiohttp kubernetes-asyncio jupyterhub jupyterhub-kubespawner)

# Install global tools
uv tool install ruff
uv tool install ty

# Install UI dependencies
cd dashboard/ui && npm ci
