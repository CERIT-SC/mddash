#!/bin/bash
set -euo pipefail

# One workspace venv for IDE type resolution and all uv run commands.
uv sync --all-packages --group dev

# Install global tools
uv tool install ruff
uv tool install ty
uv tool install zizmor

# Install frontend workspace dependencies
COREPACK_ENABLE_DOWNLOAD_PROMPT=0 pnpm install --frozen-lockfile
