#!/bin/bash
set -euo pipefail
# Runs the full notebook lifecycle: start Jupyter, then self-terminate the pod on exit.

# Webhook injects OMP_NUM_THREADS cluster-wide; GROMACS treats any present value (even
# empty) as a user-forced count and aborts GPU runs without -ntmpi.
if compgen -G "/dev/nvidia*" >/dev/null; then
    unset OMP_NUM_THREADS
fi

start-with-binder.sh "$@" || true

# After Jupyter exits (idle shutdown or crash), delete the pod so reserved
# resources are freed. MY_POD_NAME is injected via Downward API.
if [[ -n "${MY_POD_NAME:-}" ]]; then
    kubectl delete pod "$MY_POD_NAME" --grace-period=30 2>/dev/null || true
fi
