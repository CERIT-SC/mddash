#!/bin/bash
set -euo pipefail

/home/vscode/.venv/bin/pip install --upgrade pip
/home/vscode/.venv/bin/pip install -r dashboard/api/requirements-dev.txt
/home/vscode/.venv/bin/pip install aiohttp kubernetes-asyncio jupyterhub jupyterhub-kubespawner  # extra dependencies for pre_spawn_hook.py
/home/vscode/.venv/bin/pip install ruff  # Python linter
cd dashboard/ui && npm ci
