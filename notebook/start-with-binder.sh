#!/bin/bash
set -euo pipefail
# Activates the binder environment (if installed) then starts Jupyter.

WORKDIR="${WORKDIR:?Error: WORKDIR not set}"
BINDER_ENV="${WORKDIR}/.binder-env"
MARKER="${WORKDIR}/.binder-env-installed"

# Only activate if the environment was successfully installed
if [[ -f "$MARKER" ]] && [[ -x "${BINDER_ENV}/bin/python" ]]; then
    echo "Activating binder environment at $BINDER_ENV"
    # Prepend binder env to PATH
    export PATH="${BINDER_ENV}/bin:${PATH}"
    # Use binder env's python for jupyter
    export CONDA_PREFIX="$BINDER_ENV"
    export CONDA_DEFAULT_ENV="$BINDER_ENV"
else
    echo "Binder environment not found or incomplete, using base image Python"
fi

exec start-notebook.py "$@"
