# shellcheck shell=bash
# Sourced (not executed) before Jupyter or the headless setup run: one place for the runtime env rules.

# Webhook injects OMP_NUM_THREADS cluster-wide; GROMACS treats any present value (even
# empty) as a user-forced count and aborts GPU runs without -ntmpi.
if compgen -G "/dev/nvidia*" >/dev/null; then
    unset OMP_NUM_THREADS
fi

# Only activate the Binder env once its install finished.
_binder_env="${WORKDIR:?Error: WORKDIR not set}/.binder-env"
if [[ -f "${WORKDIR}/.binder-env-installed" ]] && [[ -x "${_binder_env}/bin/python" ]]; then
    echo "Activating binder environment at ${_binder_env}"
    export PATH="${_binder_env}/bin:${PATH}"
    export CONDA_PREFIX="$_binder_env"
    export CONDA_DEFAULT_ENV="$_binder_env"
else
    echo "Binder environment not found or incomplete, using base image Python"
fi
unset _binder_env
