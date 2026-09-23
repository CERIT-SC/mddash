#!/bin/bash
set -euo pipefail

# One workspace venv for IDE type resolution and all uv run commands.
uv sync --all-packages --group dev

# Install global tools
uv tool install ruff
uv tool install ty
uv tool install zizmor

pnpm config set global-bin-dir /home/vscode/.local/bin --location=global
pnpm add -g @playwright/cli@0.1.21
# Pinned to the playwright-core @mddash/e2e pins, so both tools share one
# chromium revision; system deps come from the @mddash/e2e install below.
playwright-cli install-browser chromium

# Install frontend workspace dependencies
COREPACK_ENABLE_DOWNLOAD_PROMPT=0 pnpm install --frozen-lockfile

# Playwright browser for make e2e
pnpm --filter @mddash/e2e exec playwright install --with-deps chromium
