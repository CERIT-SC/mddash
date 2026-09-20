#!/bin/bash
set -euo pipefail

# One workspace venv for IDE type resolution and all uv run commands.
uv sync --all-packages --group dev

# Install global tools
uv tool install ruff
uv tool install ty
uv tool install zizmor

# playwright-cli for agent-driven browser automation (skill lives in .agents/skills/playwright-cli)
# Browser + system deps persist in the home volume, so this is a no-op after first create.
npm install -g @playwright/cli@latest
playwright-cli install-browser chromium --with-deps

# Install frontend workspace dependencies
COREPACK_ENABLE_DOWNLOAD_PROMPT=0 pnpm install --frozen-lockfile
