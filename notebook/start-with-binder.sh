#!/bin/bash
# Wrapper that activates binder environment before starting jupyter

WORKDIR="${WORKDIR:?Error: WORKDIR not set}"
BINDER_ENV="${WORKDIR}/.binder-env"
MARKER="${WORKDIR}/.binder-env-installed"

# Only activate if the environment was successfully installed
if [[ -f "$MARKER" ]] && [[ -x "${BINDER_ENV}/bin/python" ]]; then
    echo "Activating binder environment at $BINDER_ENV"
    # Source the conda activation script to properly set up the environment
    source "${BINDER_ENV}/bin/activate"
else
    echo "Binder environment not found or incomplete, using base image Python"
fi

# Start jupyter with the original arguments
exec start-notebook.py "$@"
