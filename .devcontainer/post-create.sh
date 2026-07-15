#!/bin/bash
set -euo pipefail

# One workspace venv for IDE type resolution and all uv run commands.
uv sync --all-packages --group dev

# Install global tools
uv tool install ruff
uv tool install ty
uv tool install zizmor

# Install UI dependencies
cd dashboard/ui && COREPACK_ENABLE_DOWNLOAD_PROMPT=0 pnpm install --frozen-lockfile
