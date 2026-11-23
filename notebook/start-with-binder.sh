#!/bin/bash
set -euo pipefail
# Activates the binder environment (if installed) then starts Jupyter.

# shellcheck source=activate-env.sh
source /usr/local/bin/activate-env.sh

exec start-notebook.py "$@"
