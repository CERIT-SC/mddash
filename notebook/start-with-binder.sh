#!/bin/bash
# Wrapper that activates binder environment before starting jupyter

WORKDIR="${WORKDIR:?Error: WORKDIR not set}"
BINDER_ENV="${WORKDIR}/.binder-env"

if [[ -d "$BINDER_ENV" ]]; then
    echo "Activating binder environment at $BINDER_ENV"
    # Prepend binder env to PATH
    export PATH="${BINDER_ENV}/bin:${PATH}"
    # Use binder env's python for jupyter
    export PYTHONHOME="$BINDER_ENV"
    export CONDA_PREFIX="$BINDER_ENV"
    export CONDA_DEFAULT_ENV="$BINDER_ENV"
fi

# Start jupyter with the original arguments
exec start-notebook.py "$@"
