#!/bin/bash
set -euo pipefail

/home/vscode/.venv/bin/pip install --upgrade pip
/home/vscode/.venv/bin/pip install -r dashboard/api/requirements-dev.txt
/home/vscode/.venv/bin/pip install aiohttp kubernetes-asyncio jupyterhub kubespawner  # extra dependencies for pre_spawn_hook.py
cd dashboard/ui && npm ci
